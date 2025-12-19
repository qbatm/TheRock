import requests
import os
from pathlib import Path
import argparse

class ReportPortalDownloader:
    def __init__(self, base_url, project_name, api_token):
        """
        Initialize ReportPortal connection

        Args:
            base_url: ReportPortal URL (e.g., 'http://ucicd-reports-uat.amd.com:8080')
            project_name: Your project name in ReportPortal
            api_token: Your API token from ReportPortal user profile
        """
        self.base_url = base_url.rstrip('/')
        self.project_name = project_name
        self.api_url = f"{self.base_url}/api/v1/{project_name}"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_launch_by_name(self, launch_name):
        """Get the most recent launch by name"""
        url = f"{self.api_url}/launch"
        params = {
            "filter.eq.name": launch_name,
            "page.size": 1,
            "page.sort": "startTime,DESC"  # Get most recent first
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        content = data.get("content", [])
        if not content:
            raise Exception(f"No launch found with name: {launch_name}")

        return content[0]

    def get_launch_by_id(self, launch_id):
        """Get launch details by ID"""
        url = f"{self.api_url}/launch/{launch_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_test_items(self, launch_id, parent_id=None):
        """Get all test items for a launch (recursively)"""
        all_items = []
        page = 1
        page_size = 100

        while True:
            url = f"{self.api_url}/item"
            params = {
                "filter.eq.launchId": launch_id,
                "page.page": page,
                "page.size": page_size,
                "isLatest": False,
                "launchesLimit": 0
            }

            if parent_id:
                params["filter.eq.parentId"] = parent_id

            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            items = data.get("content", [])
            all_items.extend(items)

            # Recursively get child items
            for item in items:
                if item.get("hasChildren", False):
                    child_items = self.get_test_items(launch_id, item["id"])
                    all_items.extend(child_items)

            # Check if there are more pages
            if len(items) < page_size:
                break

            page += 1

        return all_items

    def get_logs_for_item(self, item_id, debug=False):
        """Get all logs for a test item"""
        all_logs = []

        # Method 1: Try direct endpoint
        try:
            url = f"{self.api_url}/item/{item_id}/log"
            if debug:
                print(f"    [DEBUG] Trying URL: {url}")

            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            logs = data.get("content", [])
            if debug:
                print(f"    [DEBUG] Method 1 (item/log) returned {len(logs)} logs")

            if logs:
                return logs

        except requests.exceptions.RequestException as e:
            if debug:
                print(f"    [DEBUG] Method 1 failed: {e}")

        # Method 2: Try log endpoint with filter
        try:
            url = f"{self.api_url}/log"
            params = {
                "filter.eq.item": item_id
            }
            if debug:
                print(f"    [DEBUG] Trying URL: {url} with params: {params}")

            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            logs = data.get("content", [])
            if debug:
                print(f"    [DEBUG] Method 2 (log with filter) returned {len(logs)} logs")

            if logs:
                return logs

        except requests.exceptions.RequestException as e:
            if debug:
                print(f"    [DEBUG] Method 2 failed: {e}")

        # Method 3: Try with UUID in path
        try:
            url = f"{self.api_url}/log/uuid/{item_id}"
            if debug:
                print(f"    [DEBUG] Trying URL: {url}")

            response = self.session.get(url)
            response.raise_for_status()
            logs = [response.json()]  # Single log object

            if debug:
                print(f"    [DEBUG] Method 3 (uuid path) returned {len(logs)} logs")

            if logs:
                return logs

        except requests.exceptions.RequestException as e:
            if debug:
                print(f"    [DEBUG] Method 3 failed: {e}")

        return all_logs

    def download_log_file(self, binary_content_id, output_path, log_id=None, debug=False):
        """Download a log file attachment using binary content ID"""
        # The CORRECT endpoint format (discovered from browser network tab)
        url = f"{self.base_url}/api/v1/data/{self.project_name}/{binary_content_id}"

        try:
            response = self.session.get(url, stream=True)

            if debug:
                print(f"    [DEBUG] Trying: {url}")
                print(f"    [DEBUG] Status: {response.status_code}")
                print(f"    [DEBUG] Content-Type: {response.headers.get('Content-Type')}")
                print(f"    [DEBUG] Content-Length: {response.headers.get('Content-Length')}")

            response.raise_for_status()

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Check if file has content (not empty)
            file_size = os.path.getsize(output_path)
            if file_size > 0:
                print(f"Downloaded: {output_path} ({file_size} bytes)")
                return True
            else:
                if debug:
                    print(f"    [DEBUG] File is empty")
                os.remove(output_path)
                raise Exception("Downloaded file is empty")

        except requests.exceptions.RequestException as e:
            if debug:
                print(f"    [DEBUG] Failed: {e}")
            raise e

    def download_stdout_logs(self, launch_id=None, launch_name=None, output_dir="downloads", debug=False, max_items=None):
        """
        Download all stdout.log files for a launch

        Args:
            launch_id: The launch ID (e.g., 15110) - optional if launch_name is provided
            launch_name: The launch name (e.g., "igpu_stxh-ubuntu-5936") - optional if launch_id is provided
            output_dir: Directory to save downloaded files
            debug: If True, print detailed log structure for debugging
            max_items: If set, only process this many test items (for testing)
        """
        # Get launch info by ID or name
        if launch_name:
            print(f"Fetching launch info for name: {launch_name}")
            launch = self.get_launch_by_name(launch_name)
            launch_id = launch["id"]
        elif launch_id:
            print(f"Fetching launch info for ID: {launch_id}")
            launch = self.get_launch_by_id(launch_id)
        else:
            raise ValueError("Either launch_id or launch_name must be provided")

        launch_name = launch.get("name", "unknown")

        print(f"Launch: {launch_name}")
        print(f"Fetching test items...")

        test_items = self.get_test_items(launch_id)
        print(f"Found {len(test_items)} test items")

        # Limit items if max_items is set (for testing)
        if max_items and len(test_items) > max_items:
            print(f"Limiting to first {max_items} items for testing")
            test_items = test_items[:max_items]

        stdout_count = 0

        for idx, item in enumerate(test_items, 1):
            item_id = item["id"]
            item_name = item.get("name", "unknown")
            item_type = item.get("type", "unknown")

            print(f"\n[{idx}/{len(test_items)}] Checking logs for: {item_name} (type: {item_type}, id: {item_id})")

            try:
                logs = self.get_logs_for_item(item_id, debug=debug and idx <= 3)
                print(f"  Found {len(logs)} log entries")

                for log in logs:
                    # Debug mode: print full log structure for first few logs
                    if debug and idx <= 3:
                        import json
                        print(f"\n  === DEBUG: Full log structure ===")
                        print(json.dumps(log, indent=2, default=str))
                        print(f"  === END DEBUG ===\n")

                    # Check log message for stdout.log reference
                    log_message = log.get("message", "")

                    # Check if log has an attachment
                    if log.get("binaryContent"):
                        binary_content = log["binaryContent"]

                        # Try multiple ways to get the filename
                        filename = ""
                        if log.get("file"):
                            filename = log["file"].get("name", "")
                        if not filename and binary_content:
                            filename = binary_content.get("name", "")

                        # Debug: print all attachments
                        print(f"  - Found attachment: '{filename}' | Message: '{log_message[:100]}'")

                        # Check if this is an actual file attachment (not just a log message reference)
                        # Look for messages like "[result] Attachment: attachments/XXX_stdout.txt"
                        is_stdout = False
                        is_real_attachment = False

                        # Check if message indicates this is an actual file attachment
                        if "[result] Attachment:" in log_message or "[upload " in log_message:
                            is_real_attachment = True
                            # Now check if it's a stdout file
                            if "stdout" in log_message.lower():
                                is_stdout = True

                        if is_stdout and is_real_attachment:
                            stdout_count += 1
                            print(f"  ✓ Found stdout.log!")

                            # Create a safe filename with item name
                            safe_item_name = "".join(c for c in item_name if c.isalnum() or c in (' ', '-', '_')).strip()
                            output_filename = f"{safe_item_name}_{stdout_count}_stdout.log"
                            output_path = os.path.join(output_dir, launch_name, output_filename)

                            try:
                                # Use the binary content ID to download
                                binary_id = binary_content.get("id")
                                if binary_id:
                                    self.download_log_file(binary_id, output_path, log_id=log.get("id"), debug=debug)
                                else:
                                    print(f"  ❌ No binary content ID found for log {log['id']}")
                            except Exception as e:
                                print(f"  ❌ Error downloading attachment {binary_id}: {e}")
                    elif debug and not log.get("binaryContent"):
                        # In debug mode, show logs without attachments too
                        print(f"  - No attachment | Message: '{log_message[:150]}'")
            except Exception as e:
                print(f"  ⚠️  Could not get logs for item {item_id}: {e}")
                continue

        print(f"\n✅ Downloaded {stdout_count} stdout.log files to {output_dir}/{launch_name}/")
        return stdout_count


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Download stdout.log files from ReportPortal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download by launch name
  python download_rp_logs.py --launch-name "igpu_stxh-ubuntu-5936"

  # Download by launch ID
  python download_rp_logs.py --launch-id 15004

  # Specify output directory
  python download_rp_logs.py --launch-name "igpu_stxh-ubuntu-5936" --output logs/

  # Enable debug mode
  python download_rp_logs.py --launch-name "igpu_stxh-ubuntu-5936" --debug
        """
    )

    parser.add_argument(
        '--launch-name',
        type=str,
        help='Launch name (e.g., "igpu_stxh-ubuntu-5936")'
    )
    parser.add_argument(
        '--launch-id',
        type=str,
        help='Launch ID (e.g., "15004")'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='reportportal_logs',
        help='Output directory for downloaded files (default: reportportal_logs)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        help='Limit number of test items to process (for testing)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.launch_name and not args.launch_id:
        parser.error("Either --launch-name or --launch-id must be specified")

    if args.launch_name and args.launch_id:
        parser.error("Cannot specify both --launch-name and --launch-id")

    # Configuration - prefer environment variables, fall back to defaults
    REPORT_PORTAL_URL = os.getenv("REPORT_PORTAL_URL", "http://ucicd-reports-uat.amd.com:8080")
    PROJECT_NAME = os.getenv("REPORT_PORTAL_PROJECT", "ucicd_project_slim")
    API_TOKEN = os.getenv("RP_API_TOKEN")

    if not API_TOKEN:
        print("ERROR: RP_API_TOKEN environment variable is required")
        print("Set it with: export RP_API_TOKEN=your_api_token")
        exit(1)

    # Create downloader instance
    downloader = ReportPortalDownloader(
        base_url=REPORT_PORTAL_URL,
        project_name=PROJECT_NAME,
        api_token=API_TOKEN
    )

    # Download all stdout.log files
    try:
        downloader.download_stdout_logs(
            launch_id=args.launch_id,
            launch_name=args.launch_name,
            output_dir=args.output,
            debug=args.debug,
            max_items=args.max_items
        )
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)


if __name__ == "__main__":
    main()