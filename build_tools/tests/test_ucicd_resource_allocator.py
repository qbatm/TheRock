#!/usr/bin/env python3
"""
Tests for UCICD Resource Allocator

Run with: python -m pytest build_tools/tests/test_ucicd_resource_allocator.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ucicd_resource_allocator import (
    RunnerRequirement,
    RunnerStatus,
    AllocationAction,
    load_config,
    calculate_allocation_actions,
    execute_actions,
)


class TestRunnerRequirement:
    """Tests for RunnerRequirement dataclass."""

    def test_create_runner_requirement(self):
        req = RunnerRequirement(
            label="test-runner",
            min_count=2,
            max_count=5,
            maas_tags=["gpu", "test"],
            platform="linux",
            description="Test description"
        )
        assert req.label == "test-runner"
        assert req.min_count == 2
        assert req.max_count == 5
        assert req.maas_tags == ["gpu", "test"]
        assert req.platform == "linux"
        assert req.description == "Test description"

    def test_default_description(self):
        req = RunnerRequirement(
            label="test-runner",
            min_count=1,
            max_count=3,
            maas_tags=["test"]
        )
        assert req.description == ""
        assert req.platform == "linux"  # default


class TestRunnerStatus:
    """Tests for RunnerStatus dataclass."""

    def test_create_runner_status(self):
        status = RunnerStatus(
            label="test-runner",
            connected_count=5,
            busy_count=3,
            idle_count=2
        )
        assert status.label == "test-runner"
        assert status.connected_count == 5
        assert status.busy_count == 3
        assert status.idle_count == 2


class TestAllocationAction:
    """Tests for AllocationAction dataclass."""

    def test_create_allocation_action(self):
        action = AllocationAction(
            label="test-runner",
            action="add",
            count=3,
            reason="Below minimum"
        )
        assert action.label == "test-runner"
        assert action.action == "add"
        assert action.count == 3
        assert action.reason == "Below minimum"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self):
        config = {
            "runners": [
                {
                    "label": "runner-1",
                    "maas_tags": ["gpu", "type-1"],
                    "platform": "linux",
                    "min_count": 2,
                    "max_count": 5,
                    "description": "First runner"
                },
                {
                    "label": "runner-2",
                    "maas_tags": ["cpu", "type-2"],
                    "platform": "windows",
                    "min_count": 1,
                    "max_count": 3
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        
        try:
            requirements = load_config(config_path)
            assert len(requirements) == 2
            assert requirements[0].label == "runner-1"
            assert requirements[0].maas_tags == ["gpu", "type-1"]
            assert requirements[0].platform == "linux"
            assert requirements[0].min_count == 2
            assert requirements[0].max_count == 5
            assert requirements[1].label == "runner-2"
            assert requirements[1].maas_tags == ["cpu", "type-2"]
            assert requirements[1].platform == "windows"
            assert requirements[1].description == ""
        finally:
            Path(config_path).unlink()

    def test_load_config_with_defaults(self):
        config = {
            "runners": [
                {
                    "label": "minimal-runner"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        
        try:
            requirements = load_config(config_path)
            assert len(requirements) == 1
            assert requirements[0].label == "minimal-runner"
            assert requirements[0].min_count == 1  # default
            assert requirements[0].max_count == 10  # default
            assert requirements[0].maas_tags == []  # default
            assert requirements[0].platform == "linux"  # default
        finally:
            Path(config_path).unlink()

    def test_load_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.json")

    def test_load_config_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            config_path = f.name
        
        try:
            with pytest.raises(json.JSONDecodeError):
                load_config(config_path)
        finally:
            Path(config_path).unlink()

    def test_load_empty_runners_list(self):
        config = {"runners": []}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        
        try:
            requirements = load_config(config_path)
            assert len(requirements) == 0
        finally:
            Path(config_path).unlink()


class TestCalculateAllocationActions:
    """Tests for calculate_allocation_actions function."""

    def test_needs_more_runners(self, monkeypatch):
        """Test when connected runners are below minimum."""
        def mock_get_runners(repository, label):
            return RunnerStatus(label=label, connected_count=1, busy_count=0, idle_count=1)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="test", min_count=3, max_count=5, maas_tags=["test"])
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 1
        assert actions[0].action == "add"
        assert actions[0].count == 2  # need 3, have 1
        assert actions[0].label == "test"

    def test_needs_fewer_runners(self, monkeypatch):
        """Test when connected runners are above maximum."""
        def mock_get_runners(repository, label):
            return RunnerStatus(label=label, connected_count=10, busy_count=5, idle_count=5)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="test", min_count=2, max_count=5, maas_tags=["test"])
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 1
        assert actions[0].action == "remove"
        assert actions[0].count == 5  # have 10, max 5
        assert actions[0].label == "test"

    def test_runners_in_range(self, monkeypatch):
        """Test when connected runners are within acceptable range."""
        def mock_get_runners(repository, label):
            return RunnerStatus(label=label, connected_count=3, busy_count=1, idle_count=2)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="test", min_count=2, max_count=5, maas_tags=["test"])
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 1
        assert actions[0].action == "none"
        assert actions[0].count == 0

    def test_runners_at_minimum(self, monkeypatch):
        """Test when connected runners are exactly at minimum."""
        def mock_get_runners(repository, label):
            return RunnerStatus(label=label, connected_count=2, busy_count=1, idle_count=1)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="test", min_count=2, max_count=5, maas_tags=["test"])
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 1
        assert actions[0].action == "none"

    def test_runners_at_maximum(self, monkeypatch):
        """Test when connected runners are exactly at maximum."""
        def mock_get_runners(repository, label):
            return RunnerStatus(label=label, connected_count=5, busy_count=3, idle_count=2)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="test", min_count=2, max_count=5, maas_tags=["test"])
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 1
        assert actions[0].action == "none"

    def test_multiple_requirements(self, monkeypatch):
        """Test with multiple runner requirements."""
        def mock_get_runners(repository, label):
            if label == "runner-a":
                return RunnerStatus(label=label, connected_count=0, busy_count=0, idle_count=0)
            elif label == "runner-b":
                return RunnerStatus(label=label, connected_count=10, busy_count=5, idle_count=5)
            else:
                return RunnerStatus(label=label, connected_count=3, busy_count=1, idle_count=2)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        requirements = [
            RunnerRequirement(label="runner-a", min_count=2, max_count=5, maas_tags=["type-a"]),
            RunnerRequirement(label="runner-b", min_count=2, max_count=5, maas_tags=["type-b"]),
            RunnerRequirement(label="runner-c", min_count=2, max_count=5, maas_tags=["type-c"]),
        ]
        
        actions = calculate_allocation_actions(requirements, "owner/repo")
        
        assert len(actions) == 3
        assert actions[0].action == "add"
        assert actions[0].count == 2
        assert actions[1].action == "remove"
        assert actions[1].count == 5
        assert actions[2].action == "none"


class TestExecuteActions:
    """Tests for execute_actions function."""

    def test_execute_add_action(self, monkeypatch):
        """Test executing an add action."""
        allocate_called = []
        
        def mock_allocate(action, repository):
            allocate_called.append((action, repository))
            return True
        
        monkeypatch.setattr("ucicd_resource_allocator.allocate_runners", mock_allocate)
        
        actions = [
            AllocationAction(label="test", action="add", count=2, reason="Below minimum")
        ]
        
        success, failures = execute_actions(actions, "owner/repo")
        
        assert success == 1
        assert failures == 0
        assert len(allocate_called) == 1

    def test_execute_remove_action(self, monkeypatch):
        """Test executing a remove action."""
        release_called = []
        
        def mock_release(action, repository):
            release_called.append((action, repository))
            return True
        
        monkeypatch.setattr("ucicd_resource_allocator.release_runners", mock_release)
        
        actions = [
            AllocationAction(label="test", action="remove", count=3, reason="Above maximum")
        ]
        
        success, failures = execute_actions(actions, "owner/repo")
        
        assert success == 1
        assert failures == 0
        assert len(release_called) == 1

    def test_execute_no_action(self, monkeypatch):
        """Test executing when no action is needed."""
        allocate_called = []
        release_called = []
        
        monkeypatch.setattr("ucicd_resource_allocator.allocate_runners", 
                           lambda a, r: allocate_called.append(1) or True)
        monkeypatch.setattr("ucicd_resource_allocator.release_runners", 
                           lambda a, r: release_called.append(1) or True)
        
        actions = [
            AllocationAction(label="test", action="none", count=0, reason="OK")
        ]
        
        success, failures = execute_actions(actions, "owner/repo")
        
        assert success == 0
        assert failures == 0
        assert len(allocate_called) == 0
        assert len(release_called) == 0

    def test_execute_failed_action(self, monkeypatch):
        """Test handling of failed actions."""
        def mock_allocate(action, repository):
            return False  # Simulate failure
        
        monkeypatch.setattr("ucicd_resource_allocator.allocate_runners", mock_allocate)
        
        actions = [
            AllocationAction(label="test", action="add", count=2, reason="Below minimum")
        ]
        
        success, failures = execute_actions(actions, "owner/repo")
        
        assert success == 0
        assert failures == 1

    def test_execute_mixed_actions(self, monkeypatch):
        """Test executing multiple actions with mixed results."""
        call_count = [0]
        
        def mock_allocate(action, repository):
            call_count[0] += 1
            return call_count[0] != 2  # Fail on second call
        
        def mock_release(action, repository):
            return True
        
        monkeypatch.setattr("ucicd_resource_allocator.allocate_runners", mock_allocate)
        monkeypatch.setattr("ucicd_resource_allocator.release_runners", mock_release)
        
        actions = [
            AllocationAction(label="test1", action="add", count=1, reason="Below minimum"),
            AllocationAction(label="test2", action="add", count=1, reason="Below minimum"),
            AllocationAction(label="test3", action="remove", count=1, reason="Above maximum"),
        ]
        
        success, failures = execute_actions(actions, "owner/repo")
        
        assert success == 2  # First add and remove succeed
        assert failures == 1  # Second add fails


class TestIntegration:
    """Integration tests using the actual config file format."""

    def test_full_workflow(self, monkeypatch):
        """Test the full workflow from config to actions."""
        config = {
            "runners": [
                {"label": "runner-1", "maas_tags": ["type-1"], "min_count": 3, "max_count": 5},
                {"label": "runner-2", "maas_tags": ["type-2"], "min_count": 1, "max_count": 2},
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        
        def mock_get_runners(repository, label):
            if label == "runner-1":
                return RunnerStatus(label=label, connected_count=1, busy_count=0, idle_count=1)
            else:
                return RunnerStatus(label=label, connected_count=2, busy_count=1, idle_count=1)
        
        monkeypatch.setattr("ucicd_resource_allocator.get_current_runners", mock_get_runners)
        
        try:
            requirements = load_config(config_path)
            actions = calculate_allocation_actions(requirements, "owner/repo")
            
            assert len(actions) == 2
            # runner-1: has 1, needs 3 -> add 2
            assert actions[0].action == "add"
            assert actions[0].count == 2
            # runner-2: has 2, max 2 -> OK
            assert actions[1].action == "none"
        finally:
            Path(config_path).unlink()
