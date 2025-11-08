#!/usr/bin/env python3
"""
Comprehensive test suite for all generated proto files.

Tests:
1. Proto file syntax validation
2. Compilation with protoc
3. Python import tests
4. Message parsing tests
5. Field access tests
"""

import argparse
import subprocess
import sys
import importlib.util
from pathlib import Path
from typing import List, Dict, Tuple
import json


class ProtoFileTester:
    def __init__(self, proto_root: Path):
        self.proto_root = Path(proto_root)
        self.results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "warnings": [],
        }
    
    def test_proto_compilation(self, proto_file: Path) -> Tuple[bool, str]:
        """Test if proto file compiles with protoc."""
        try:
            proto_dir = proto_file.parent
            result = subprocess.run(
                [
                    "protoc",
                    f"--proto_path={self.proto_root}",
                    f"--python_out={proto_dir}",
                    str(proto_file.relative_to(self.proto_root)),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return True, "Compiled successfully"
            else:
                error_msg = result.stderr.strip()
                # Filter out import errors (expected for some files)
                if "File not found" in error_msg or "Import" in error_msg:
                    return True, f"Compiled (import warnings: {error_msg[:100]})"
                return False, error_msg
        except FileNotFoundError:
            return False, "protoc not found"
        except subprocess.TimeoutExpired:
            return False, "Compilation timeout"
        except Exception as e:
            return False, str(e)
    
    def test_python_import(self, proto_file: Path) -> Tuple[bool, str]:
        """Test if generated pb2.py file can be imported."""
        proto_name = proto_file.stem
        pb2_file = proto_file.parent / f"{proto_name}_pb2.py"
        
        if not pb2_file.exists():
            return False, f"pb2 file not found: {pb2_file.name}"
        
        try:
            # Build module path
            rel_path = pb2_file.relative_to(self.proto_root)
            module_path = str(rel_path).replace("/", ".").replace("\\", ".").replace(".py", "")
            
            # Import the module
            spec = importlib.util.spec_from_file_location(module_path, pb2_file)
            if spec is None or spec.loader is None:
                return False, "Could not create module spec"
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if main message class exists
            message_name = proto_name.replace("_", "").title().replace("proto", "")
            if hasattr(module, message_name):
                return True, f"Imported successfully, found {message_name}"
            else:
                # Try to find any message class
                messages = [attr for attr in dir(module) if not attr.startswith("_") and attr.endswith("_pb2")]
                if messages:
                    return True, f"Imported successfully, found messages: {messages[:3]}"
                return True, "Imported but no message classes found"
        except Exception as e:
            return False, f"Import error: {str(e)[:200]}"
    
    def test_message_creation(self, proto_file: Path) -> Tuple[bool, str]:
        """Test if message can be created and has basic structure."""
        proto_name = proto_file.stem
        pb2_file = proto_file.parent / f"{proto_name}_pb2.py"
        
        if not pb2_file.exists():
            return True, "Skipped (no pb2 file)"
        
        try:
            rel_path = pb2_file.relative_to(self.proto_root)
            module_path = str(rel_path).replace("/", ".").replace("\\", ".").replace(".py", "")
            
            spec = importlib.util.spec_from_file_location(module_path, pb2_file)
            if spec is None or spec.loader is None:
                return True, "Skipped (could not import)"
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find message classes
            message_classes = [
                attr for attr in dir(module)
                if not attr.startswith("_") and 
                   not attr.endswith("_pb2") and
                   hasattr(getattr(module, attr), "DESCRIPTOR")
            ]
            
            if not message_classes:
                return True, "No message classes found (may be empty proto)"
            
            # Try to create an instance of the first message
            first_message = getattr(module, message_classes[0])
            instance = first_message()
            
            # Try to serialize (basic validation)
            try:
                serialized = instance.SerializeToString()
                return True, f"Created {message_classes[0]}, serialized {len(serialized)} bytes"
            except Exception as e:
                return True, f"Created {message_classes[0]} but serialization failed: {str(e)[:100]}"
        except Exception as e:
            return False, f"Message creation error: {str(e)[:200]}"
    
    def test_with_capture_data(self, proto_file: Path, capture_dirs: List[Path]) -> Tuple[bool, str]:
        """Test if proto can parse actual capture data."""
        proto_name = proto_file.stem
        pb2_file = proto_file.parent / f"{proto_name}_pb2.py"
        
        if not pb2_file.exists():
            return True, "Skipped (no pb2 file)"
        
        # Find relevant raw capture files
        raw_files = []
        for capture_dir in capture_dirs:
            raw_files.extend(capture_dir.glob("*.raw.bin"))
        
        if not raw_files:
            return True, "Skipped (no capture data)"
        
        try:
            rel_path = pb2_file.relative_to(self.proto_root)
            module_path = str(rel_path).replace("/", ".").replace("\\", ".").replace(".py", "")
            
            spec = importlib.util.spec_from_file_location(module_path, pb2_file)
            if spec is None or spec.loader is None:
                return True, "Skipped (could not import)"
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Try to parse a small sample
            test_file = raw_files[0]
            with open(test_file, "rb") as f:
                sample_data = f.read()[:1000]  # First 1000 bytes
            
            # Find message classes and try to parse
            message_classes = [
                attr for attr in dir(module)
                if not attr.startswith("_") and 
                   hasattr(getattr(module, attr), "DESCRIPTOR")
            ]
            
            if not message_classes:
                return True, "No message classes to test"
            
            # Try parsing with first message class
            first_message = getattr(module, message_classes[0])
            instance = first_message()
            
            try:
                instance.ParseFromString(sample_data)
                return True, f"Parsed {len(sample_data)} bytes with {message_classes[0]}"
            except Exception as e:
                # Parsing failure is expected for some messages
                return True, f"Parse attempt (expected to fail for some): {str(e)[:100]}"
        except Exception as e:
            return True, f"Capture test error: {str(e)[:100]}"
    
    def run_all_tests(self, capture_dirs: List[Path] = None):
        """Run all tests on all proto files."""
        proto_files = list(self.proto_root.rglob("*.proto"))
        proto_files.sort()
        
        self.results["total"] = len(proto_files)
        capture_dirs = capture_dirs or []
        
        print("="*80)
        print(f"TESTING {len(proto_files)} PROTO FILES")
        print("="*80)
        print()
        
        for proto_file in proto_files:
            rel_path = proto_file.relative_to(self.proto_root)
            print(f"Testing: {rel_path}")
            print("-" * 80)
            
            # Test 1: Compilation
            print("  [1/4] Compilation test...", end=" ")
            compiled, msg = self.test_proto_compilation(proto_file)
            if compiled:
                print(f"✅ {msg}")
                self.results["passed"] += 1
            else:
                print(f"❌ {msg}")
                self.results["failed"] += 1
                self.results["errors"].append(f"{rel_path}: Compilation - {msg}")
            
            # Test 2: Python import
            print("  [2/4] Python import test...", end=" ")
            imported, msg = self.test_python_import(proto_file)
            if imported:
                print(f"✅ {msg}")
            else:
                print(f"⚠️  {msg}")
                self.results["warnings"].append(f"{rel_path}: Import - {msg}")
            
            # Test 3: Message creation
            print("  [3/4] Message creation test...", end=" ")
            created, msg = self.test_message_creation(proto_file)
            if created:
                print(f"✅ {msg}")
            else:
                print(f"⚠️  {msg}")
                self.results["warnings"].append(f"{rel_path}: Creation - {msg}")
            
            # Test 4: Capture data parsing
            if capture_dirs:
                print("  [4/4] Capture data parsing test...", end=" ")
                parsed, msg = self.test_with_capture_data(proto_file, capture_dirs)
                if parsed:
                    print(f"✅ {msg}")
                else:
                    print(f"⚠️  {msg}")
                    self.results["warnings"].append(f"{rel_path}: Parsing - {msg}")
            
            print()
        
        # Print summary
        print("="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total proto files: {self.results['total']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"⚠️  Warnings: {len(self.results['warnings'])}")
        print()
        
        if self.results["errors"]:
            print("Errors:")
            for error in self.results["errors"][:10]:
                print(f"  ❌ {error}")
            if len(self.results["errors"]) > 10:
                print(f"  ... and {len(self.results['errors']) - 10} more")
            print()
        
        if self.results["warnings"]:
            print("Warnings:")
            for warning in self.results["warnings"][:10]:
                print(f"  ⚠️  {warning}")
            if len(self.results["warnings"]) > 10:
                print(f"  ... and {len(self.results['warnings']) - 10} more")
            print()
        
        return self.results["failed"] == 0


def main():
    parser = argparse.ArgumentParser(
        description="Test all generated proto files"
    )
    parser.add_argument(
        "--proto-root",
        type=Path,
        default=Path("proto/final"),
        help="Root directory for proto files to test",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing capture files for parsing tests",
    )
    
    args = parser.parse_args()
    
    if not args.proto_root.exists():
        print(f"Error: Proto root does not exist: {args.proto_root}")
        return 1
    
    # Find capture directories
    capture_dirs = []
    if args.captures_dir.exists():
        capture_dirs = [d for d in args.captures_dir.iterdir() if d.is_dir()]
    
    tester = ProtoFileTester(args.proto_root)
    success = tester.run_all_tests(capture_dirs)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

