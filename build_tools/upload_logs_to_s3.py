#!/usr/bin/env python3
"""
Upload logs to Amazon S3.

This script zips a specified log directory and uploads it to an S3 bucket.
Linux only - Windows is not supported.

Usage:
    python upload_logs_to_s3.py --log-dir /path/to/logs --bucket my-bucket \
        --s3-key logs/archive.zip --aws-access-key SAMPLE_KEY \
        --aws-secret-key SAMPLE_SECRET_KEY

    # Or using environment variables for credentials:
    export AWS_ACCESS_KEY_ID=SAMPLE_KEY
    export AWS_SECRET_ACCESS_KEY=SAMPLE_SECRET_KEY
    python upload_logs_to_s3.py --log-dir /path/to/logs --bucket my-bucket --s3-key logs/archive.zip
"""

import argparse
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("ERROR: boto3 is required. Install it with: pip install boto3", file=sys.stderr)
    sys.exit(1)


def check_platform() -> None:
    """Check if running on a supported platform (Linux only)."""
    current_platform = platform.system().lower()
    if current_platform == "windows":
        print("ERROR: This script is not supported on Windows.", file=sys.stderr)
        print("Please run this script on a Linux machine.", file=sys.stderr)
        sys.exit(1)
    elif current_platform != "linux":
        print(f"WARNING: This script is designed for Linux. Current platform: {current_platform}", file=sys.stderr)


def validate_log_directory(log_dir: str) -> Path:
    """
    Validate that the log directory exists and is accessible.

    Args:
        log_dir: Path to the log directory.

    Returns:
        Path object for the validated directory.

    Raises:
        SystemExit: If directory doesn't exist or is not readable.
    """
    path = Path(log_dir).resolve()

    if not path.exists():
        print(f"ERROR: Log directory does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    if not path.is_dir():
        print(f"ERROR: Path is not a directory: {path}", file=sys.stderr)
        sys.exit(1)

    if not os.access(path, os.R_OK):
        print(f"ERROR: Log directory is not readable: {path}", file=sys.stderr)
        sys.exit(1)

    return path


def generate_archive_name(log_dir: Path, custom_name: str | None = None) -> str:
    """
    Generate a name for the zip archive.

    Args:
        log_dir: Path to the log directory.
        custom_name: Optional custom name for the archive.

    Returns:
        Archive name (without .zip extension).
    """
    if custom_name:
        # Remove .zip extension if provided
        return custom_name.removesuffix(".zip")

    # Generate name based on directory name and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = log_dir.name
    return f"{dir_name}_{timestamp}"


def create_zip_archive(log_dir: Path, archive_name: str, temp_dir: str | None = None) -> Path:
    """
    Create a zip archive of the log directory.

    Args:
        log_dir: Path to the log directory to archive.
        archive_name: Name for the archive (without extension).
        temp_dir: Optional temporary directory for the archive.

    Returns:
        Path to the created zip file.
    """
    if temp_dir is None:
        temp_dir = tempfile.gettempdir()

    archive_path = Path(temp_dir) / archive_name

    print(f"Creating zip archive: {archive_path}.zip")
    print(f"Source directory: {log_dir}")

    # shutil.make_archive returns the path with extension
    created_archive = shutil.make_archive(
        base_name=str(archive_path),
        format="zip",
        root_dir=log_dir.parent,
        base_dir=log_dir.name
    )

    archive_file = Path(created_archive)
    size_mb = archive_file.stat().st_size / (1024 * 1024)
    print(f"Archive created: {archive_file} ({size_mb:.2f} MB)")

    return archive_file


def create_s3_client(
    aws_access_key: str | None = None,
    aws_secret_key: str | None = None,
    aws_region: str | None = None
) -> "boto3.client":
    """
    Create an S3 client with the provided or environment credentials.

    Args:
        aws_access_key: AWS access key ID (optional, uses env var if not provided).
        aws_secret_key: AWS secret access key (optional, uses env var if not provided).
        aws_region: AWS region (optional, defaults to us-east-1).

    Returns:
        Configured boto3 S3 client.
    """
    # Use provided credentials or fall back to environment variables
    access_key = aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = aws_secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = aws_region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    if access_key and secret_key:
        return boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
    else:
        # Let boto3 use its default credential chain (env vars, ~/.aws/credentials, IAM role, etc.)
        return boto3.client("s3", region_name=region)


def upload_to_s3(
    s3_client: "boto3.client",
    file_path: Path,
    bucket: str,
    s3_key: str
) -> str:
    """
    Upload a file to S3.

    Args:
        s3_client: Configured boto3 S3 client.
        file_path: Path to the file to upload.
        bucket: S3 bucket name.
        s3_key: S3 object key (path within bucket).

    Returns:
        S3 URI of the uploaded file.

    Raises:
        SystemExit: If upload fails.
    """
    print(f"Uploading to s3://{bucket}/{s3_key}")

    try:
        file_size = file_path.stat().st_size

        # Use multipart upload for large files (> 100MB)
        if file_size > 100 * 1024 * 1024:
            print("Using multipart upload for large file...")
            from boto3.s3.transfer import TransferConfig
            config = TransferConfig(
                multipart_threshold=100 * 1024 * 1024,
                max_concurrency=10,
                multipart_chunksize=100 * 1024 * 1024
            )
            s3_client.upload_file(str(file_path), bucket, s3_key, Config=config)
        else:
            s3_client.upload_file(str(file_path), bucket, s3_key)

        s3_uri = f"s3://{bucket}/{s3_key}"
        print(f"Upload successful: {s3_uri}")
        return s3_uri

    except NoCredentialsError:
        print("ERROR: AWS credentials not found.", file=sys.stderr)
        print("Provide credentials via --aws-access-key and --aws-secret-key,", file=sys.stderr)
        print("or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.", file=sys.stderr)
        sys.exit(1)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"ERROR: S3 upload failed ({error_code}): {error_msg}", file=sys.stderr)
        sys.exit(1)


def cleanup_temp_file(file_path: Path) -> None:
    """
    Remove temporary file.

    Args:
        file_path: Path to the file to remove.
    """
    try:
        if file_path.exists():
            file_path.unlink()
            print(f"Cleaned up temporary file: {file_path}")
    except OSError as e:
        print(f"WARNING: Failed to clean up temporary file: {e}", file=sys.stderr)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Zip and upload logs to Amazon S3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using command line credentials:
  %(prog)s --log-dir /var/log/myapp --bucket my-logs-bucket \\
      --s3-key logs/myapp/archive.zip \\
      --aws-access-key SAMPLE_KEY \\
      --aws-secret-key SAMPLE_SECRET_KEY

  # Using environment variables for credentials:
  export AWS_ACCESS_KEY_ID=SAMPLE_KEY
  export AWS_SECRET_ACCESS_KEY=SAMPLE_SECRET_KEY
  %(prog)s --log-dir /var/log/myapp --bucket my-logs-bucket

  # With custom archive name and region:
  %(prog)s --log-dir /var/log/myapp --bucket my-logs-bucket \\
      --archive-name myapp-logs-dec2024 --region eu-west-1
        """
    )

    # Required arguments
    parser.add_argument(
        "--log-dir", "-l",
        required=True,
        help="Path to the log directory to archive and upload."
    )
    parser.add_argument(
        "--bucket", "-b",
        required=True,
        help="S3 bucket name."
    )

    # Optional arguments
    parser.add_argument(
        "--s3-key", "-k",
        help="S3 object key (path within bucket). Defaults to <archive-name>.zip"
    )
    parser.add_argument(
        "--archive-name", "-n",
        help="Custom name for the zip archive. Defaults to <dirname>_<timestamp>."
    )
    parser.add_argument(
        "--aws-access-key",
        help="AWS access key ID. Can also be set via AWS_ACCESS_KEY_ID env var."
    )
    parser.add_argument(
        "--aws-secret-key",
        help="AWS secret access key. Can also be set via AWS_SECRET_ACCESS_KEY env var."
    )
    parser.add_argument(
        "--region", "-r",
        default=None,
        help="AWS region. Defaults to AWS_DEFAULT_REGION env var or us-east-1."
    )
    parser.add_argument(
        "--keep-local",
        action="store_true",
        help="Keep the local zip file after upload."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create archive but don't upload to S3."
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # Check platform first
    check_platform()

    # Parse arguments
    args = parse_arguments()

    # Validate log directory
    log_dir = validate_log_directory(args.log_dir)

    # Generate archive name
    archive_name = generate_archive_name(log_dir, args.archive_name)

    # Create zip archive
    archive_path = create_zip_archive(log_dir, archive_name)

    try:
        if args.dry_run:
            print(f"DRY RUN: Would upload {archive_path} to s3://{args.bucket}/{args.s3_key or archive_name + '.zip'}")
            if not args.keep_local:
                cleanup_temp_file(archive_path)
            return 0

        # Determine S3 key
        s3_key = args.s3_key or f"{archive_name}.zip"

        # Create S3 client
        s3_client = create_s3_client(
            aws_access_key=args.aws_access_key,
            aws_secret_key=args.aws_secret_key,
            aws_region=args.region
        )

        # Upload to S3
        s3_uri = upload_to_s3(s3_client, archive_path, args.bucket, s3_key)

        print(f"\nSuccess! Logs uploaded to: {s3_uri}")
        return 0

    finally:
        # Cleanup unless --keep-local is specified
        if not args.keep_local:
            cleanup_temp_file(archive_path)
        else:
            print(f"Local archive kept at: {archive_path}")


if __name__ == "__main__":
    sys.exit(main())