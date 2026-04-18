#!/usr/bin/env python3
"""
Code Quality Check Script
========================

This script runs various code quality checks including:
- Type checking with mypy
- Code style checking with flake8
- Security analysis with bandit
- Import sorting with isort
- Code formatting with black

Usage:
    python scripts/code_quality_check.py [--fix] [--module MODULE_NAME]
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


class CodeQualityChecker:
    """Code quality checker for the Hydrology framework."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.modules = [
            'hydro_model',
            'common',
            'api',
            'dl_model',
            'preprocessing',
            'utils',
            'gui'
        ]
    
    def run_mypy(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Run mypy type checking."""
        print("\n🔍 Running mypy type checking...")
        
        if module:
            cmd = ['python', '-m', 'mypy', module]
        else:
            cmd = ['python', '-m', 'mypy'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print("✅ MyPy: No type errors found")
                return True, result.stdout
            else:
                print("❌ MyPy: Type errors found")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ MyPy: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ MyPy: mypy not found. Install with: pip install mypy")
            return False, "mypy not found"
    
    def run_flake8(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Run flake8 style checking."""
        print("\n🎨 Running flake8 style checking...")
        
        if module:
            cmd = ['python', '-m', 'flake8', module]
        else:
            cmd = ['python', '-m', 'flake8'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print("✅ Flake8: No style issues found")
                return True, result.stdout
            else:
                print("❌ Flake8: Style issues found")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ Flake8: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ Flake8: flake8 not found. Install with: pip install flake8")
            return False, "flake8 not found"
    
    def run_bandit(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Run bandit security analysis."""
        print("\n🔒 Running bandit security analysis...")
        
        if module:
            cmd = ['python', '-m', 'bandit', '-r', module, '-f', 'txt']
        else:
            cmd = ['python', '-m', 'bandit', '-r'] + self.modules + ['-f', 'txt']
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print("✅ Bandit: No security issues found")
                return True, result.stdout
            else:
                print("⚠️ Bandit: Security issues found")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ Bandit: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ Bandit: bandit not found. Install with: pip install bandit")
            return False, "bandit not found"
    
    def run_isort_check(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Check import sorting with isort."""
        print("\n📦 Checking import sorting with isort...")
        
        if module:
            cmd = ['python', '-m', 'isort', '--check-only', '--diff', module]
        else:
            cmd = ['python', '-m', 'isort', '--check-only', '--diff'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ isort: Import sorting is correct")
                return True, result.stdout
            else:
                print("❌ isort: Import sorting issues found")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ isort: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ isort: isort not found. Install with: pip install isort")
            return False, "isort not found"
    
    def run_isort_fix(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Fix import sorting with isort."""
        print("\n🔧 Fixing import sorting with isort...")
        
        if module:
            cmd = ['python', '-m', 'isort', module]
        else:
            cmd = ['python', '-m', 'isort'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ isort: Import sorting fixed")
                return True, result.stdout
            else:
                print("❌ isort: Failed to fix import sorting")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ isort: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ isort: isort not found. Install with: pip install isort")
            return False, "isort not found"
    
    def run_black_check(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Check code formatting with black."""
        print("\n🖤 Checking code formatting with black...")
        
        if module:
            cmd = ['python', '-m', 'black', '--check', '--diff', module]
        else:
            cmd = ['python', '-m', 'black', '--check', '--diff'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ Black: Code formatting is correct")
                return True, result.stdout
            else:
                print("❌ Black: Code formatting issues found")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ Black: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ Black: black not found. Install with: pip install black")
            return False, "black not found"
    
    def run_black_fix(self, module: Optional[str] = None) -> Tuple[bool, str]:
        """Fix code formatting with black."""
        print("\n🔧 Fixing code formatting with black...")
        
        if module:
            cmd = ['python', '-m', 'black', module]
        else:
            cmd = ['python', '-m', 'black'] + self.modules
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ Black: Code formatting fixed")
                return True, result.stdout
            else:
                print("❌ Black: Failed to fix code formatting")
                print(result.stdout)
                return False, result.stdout
                
        except subprocess.TimeoutExpired:
            print("⏰ Black: Timeout expired")
            return False, "Timeout"
        except FileNotFoundError:
            print("❌ Black: black not found. Install with: pip install black")
            return False, "black not found"
    
    def run_all_checks(self, module: Optional[str] = None, fix: bool = False) -> bool:
        """Run all code quality checks."""
        print(f"🚀 Running code quality checks for Hydrology framework")
        if module:
            print(f"📁 Target module: {module}")
        else:
            print(f"📁 Target modules: {', '.join(self.modules)}")
        
        results = []
        
        # Fix formatting and imports if requested
        if fix:
            self.run_isort_fix(module)
            self.run_black_fix(module)
        
        # Run checks
        results.append(self.run_mypy(module))
        results.append(self.run_flake8(module))
        results.append(self.run_bandit(module))
        results.append(self.run_isort_check(module))
        results.append(self.run_black_check(module))
        
        # Summary
        passed = sum(1 for success, _ in results if success)
        total = len(results)
        
        print(f"\n📊 Summary: {passed}/{total} checks passed")
        
        if passed == total:
            print("🎉 All code quality checks passed!")
            return True
        else:
            print("❌ Some code quality checks failed. Please fix the issues above.")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run code quality checks for the Hydrology framework"
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Automatically fix formatting and import issues'
    )
    parser.add_argument(
        '--module',
        type=str,
        help='Run checks on a specific module only'
    )
    
    args = parser.parse_args()
    
    # Find project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    # Validate module if specified
    if args.module:
        module_path = project_root / args.module
        if not module_path.exists():
            print(f"❌ Module '{args.module}' not found")
            sys.exit(1)
    
    # Run checks
    checker = CodeQualityChecker(project_root)
    success = checker.run_all_checks(args.module, args.fix)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()