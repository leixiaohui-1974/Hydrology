"""
Git Version Control Integration for Hydrology Projects
====================================================
This module provides Git integration for hydrological modeling projects,
including version control, branching, and collaboration features.
"""
import os
import git
import json
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import logging
import subprocess
import shutil
from pathlib import Path


class GitIntegration:
    """
    Git integration for hydrological modeling projects.
    """
    
    def __init__(self, project_path: str):
        """
        Initialize Git integration for a project.
        
        Args:
            project_path: Path to the project directory
        """
        self.project_path = os.path.abspath(project_path)
        self.repo = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize or load repository
        self._initialize_repo()
        
    def _initialize_repo(self):
        """Initialize or load the Git repository."""
        git_dir = os.path.join(self.project_path, '.git')
        
        if os.path.exists(git_dir):
            try:
                self.repo = git.Repo(self.project_path)
                self.logger.info(f"Loaded existing Git repository at {self.project_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load existing repository: {e}")
                self.repo = None
        else:
            try:
                self.repo = git.Repo.init(self.project_path)
                self.logger.info(f"Initialized new Git repository at {self.project_path}")
            except Exception as e:
                self.logger.error(f"Failed to initialize repository: {e}")
                self.repo = None
                
    def is_repository(self) -> bool:
        """Check if the project is a Git repository."""
        return self.repo is not None
        
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current Git status.
        
        Returns:
            Dictionary with repository status information
        """
        if not self.is_repository():
            return {'error': 'Not a Git repository'}
            
        try:
            # Get current branch
            current_branch = self.repo.active_branch.name
            
            # Get status
            status = {
                'branch': current_branch,
                'is_clean': not self.repo.is_dirty(),
                'untracked_files': [],
                'modified_files': [],
                'staged_files': [],
                'ahead': 0,
                'behind': 0,
                'last_commit': None
            }
            
            # Get untracked files
            status['untracked_files'] = self.repo.untracked_files
            
            # Get modified files
            for item in self.repo.index.diff(None):
                status['modified_files'].append(item.a_path)
                
            # Get staged files
            for item in self.repo.index.diff('HEAD'):
                status['staged_files'].append(item.a_path)
                
            # Get commit information
            if self.repo.head.is_valid():
                last_commit = self.repo.head.commit
                status['last_commit'] = {
                    'hash': last_commit.hexsha[:8],
                    'message': last_commit.message.strip(),
                    'author': f"{last_commit.author.name} <{last_commit.author.email}>",
                    'date': last_commit.committed_datetime.isoformat()
                }
                
            # Get remote information
            if self.repo.remotes:
                origin = self.repo.remotes.origin
                if origin.exists():
                    try:
                        # Get ahead/behind information
                        local_branch = self.repo.active_branch
                        remote_branch = origin.refs[local_branch.name]
                        
                        ahead_behind = self.repo.iter_commits(
                            f"{local_branch.name}..{remote_branch.name}"
                        )
                        status['ahead'] = len(list(ahead_behind))
                        
                        behind_ahead = self.repo.iter_commits(
                            f"{remote_branch.name}..{local_branch.name"
                        )
                        status['behind'] = len(list(behind_ahead))
                        
                    except Exception as e:
                        self.logger.warning(f"Could not determine ahead/behind: {e}")
                        
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get status: {e}")
            return {'error': str(e)}
            
    def add_files(self, file_patterns: List[str] = None) -> bool:
        """
        Add files to the staging area.
        
        Args:
            file_patterns: List of file patterns to add (None for all)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            if file_patterns:
                for pattern in file_patterns:
                    self.repo.index.add(pattern)
            else:
                self.repo.index.add('*')
                
            self.logger.info("Files added to staging area")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add files: {e}")
            return False
            
    def commit(self, message: str, author: str = None) -> bool:
        """
        Commit staged changes.
        
        Args:
            message: Commit message
            author: Author information (format: "Name <email>")
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            # Set author if provided
            if author:
                self.repo.config_writer().set_value("user", "name", author.split('<')[0].strip())
                email = author.split('<')[1].split('>')[0].strip()
                self.repo.config_writer().set_value("user", "email", email)
                
            # Commit
            self.repo.index.commit(message)
            self.logger.info(f"Changes committed: {message}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to commit: {e}")
            return False
            
    def create_branch(self, branch_name: str, checkout: bool = True) -> bool:
        """
        Create a new branch.
        
        Args:
            branch_name: Name of the new branch
            checkout: Whether to checkout the new branch
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            # Create new branch
            new_branch = self.repo.create_head(branch_name)
            
            if checkout:
                new_branch.checkout()
                self.logger.info(f"Created and checked out branch: {branch_name}")
            else:
                self.logger.info(f"Created branch: {branch_name}")
                
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create branch: {e}")
            return False
            
    def checkout_branch(self, branch_name: str) -> bool:
        """
        Checkout a branch.
        
        Args:
            branch_name: Name of the branch to checkout
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            # Check if branch exists
            if branch_name in [branch.name for branch in self.repo.branches]:
                self.repo.branches[branch_name].checkout()
                self.logger.info(f"Checked out branch: {branch_name}")
                return True
            else:
                self.logger.error(f"Branch '{branch_name}' not found")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to checkout branch: {e}")
            return False
            
    def list_branches(self) -> List[Dict[str, Any]]:
        """
        List all branches.
        
        Returns:
            List of branch information
        """
        if not self.is_repository():
            return []
            
        try:
            branches = []
            current_branch = self.repo.active_branch.name
            
            for branch in self.repo.branches:
                branch_info = {
                    'name': branch.name,
                    'is_current': branch.name == current_branch,
                    'last_commit': None
                }
                
                # Get last commit information
                if branch.commit:
                    commit = branch.commit
                    branch_info['last_commit'] = {
                        'hash': commit.hexsha[:8],
                        'message': commit.message.strip(),
                        'date': commit.committed_datetime.isoformat()
                    }
                    
                branches.append(branch_info)
                
            return branches
            
        except Exception as e:
            self.logger.error(f"Failed to list branches: {e}")
            return []
            
    def merge_branch(self, source_branch: str, target_branch: str = None) -> bool:
        """
        Merge a branch into the current branch.
        
        Args:
            source_branch: Name of the source branch to merge
            target_branch: Name of the target branch (default: current)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            if target_branch:
                # Checkout target branch first
                self.checkout_branch(target_branch)
                
            # Merge source branch
            self.repo.git.merge(source_branch)
            self.logger.info(f"Merged branch '{source_branch}' into '{self.repo.active_branch.name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to merge branch: {e}")
            return False
            
    def delete_branch(self, branch_name: str, force: bool = False) -> bool:
        """
        Delete a branch.
        
        Args:
            branch_name: Name of the branch to delete
            force: Force deletion even if not merged
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            # Check if trying to delete current branch
            if branch_name == self.repo.active_branch.name:
                self.logger.error("Cannot delete current branch")
                return False
                
            # Delete branch
            if force:
                self.repo.delete_head(branch_name, force=True)
            else:
                self.repo.delete_head(branch_name)
                
            self.logger.info(f"Deleted branch: {branch_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete branch: {e}")
            return False
            
    def get_commit_history(self, max_count: int = 50) -> List[Dict[str, Any]]:
        """
        Get commit history.
        
        Args:
            max_count: Maximum number of commits to return
            
        Returns:
            List of commit information
        """
        if not self.is_repository():
            return []
            
        try:
            commits = []
            for commit in self.repo.iter_commits('HEAD', max_count=max_count):
                commit_info = {
                    'hash': commit.hexsha[:8],
                    'full_hash': commit.hexsha,
                    'message': commit.message.strip(),
                    'author': f"{commit.author.name} <{commit.author.email}>",
                    'date': commit.committed_datetime.isoformat(),
                    'files_changed': len(commit.stats.files)
                }
                commits.append(commit_info)
                
            return commits
            
        except Exception as e:
            self.logger.error(f"Failed to get commit history: {e}")
            return []
            
    def get_file_history(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Get history of changes for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of commit information for the file
        """
        if not self.is_repository():
            return []
            
        try:
            commits = []
            for commit in self.repo.iter_commits('HEAD', paths=file_path):
                commit_info = {
                    'hash': commit.hexsha[:8],
                    'message': commit.message.strip(),
                    'author': f"{commit.author.name} <{commit.author.email}>",
                    'date': commit.committed_datetime.isoformat()
                }
                commits.append(commit_info)
                
            return commits
            
        except Exception as e:
            self.logger.error(f"Failed to get file history: {e}")
            return []
            
    def create_tag(self, tag_name: str, message: str = None, commit_hash: str = None) -> bool:
        """
        Create a tag.
        
        Args:
            tag_name: Name of the tag
            message: Tag message
            commit_hash: Commit hash to tag (default: HEAD)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            if commit_hash:
                commit = self.repo.commit(commit_hash)
            else:
                commit = self.repo.head.commit
                
            if message:
                self.repo.create_tag(tag_name, ref=commit, message=message)
            else:
                self.repo.create_tag(tag_name, ref=commit)
                
            self.logger.info(f"Created tag: {tag_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create tag: {e}")
            return False
            
    def list_tags(self) -> List[Dict[str, Any]]:
        """
        List all tags.
        
        Returns:
            List of tag information
        """
        if not self.is_repository():
            return []
            
        try:
            tags = []
            for tag in self.repo.tags:
                tag_info = {
                    'name': tag.name,
                    'commit_hash': tag.commit.hexsha[:8],
                    'message': tag.tag.message if tag.tag else None,
                    'date': tag.commit.committed_datetime.isoformat()
                }
                tags.append(tag_info)
                
            return tags
            
        except Exception as e:
            self.logger.error(f"Failed to list tags: {e}")
            return []
            
    def add_remote(self, name: str, url: str) -> bool:
        """
        Add a remote repository.
        
        Args:
            name: Name of the remote
            url: URL of the remote repository
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            self.repo.create_remote(name, url)
            self.logger.info(f"Added remote '{name}': {url}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add remote: {e}")
            return False
            
    def list_remotes(self) -> List[Dict[str, str]]:
        """
        List remote repositories.
        
        Returns:
            List of remote information
        """
        if not self.is_repository():
            return []
            
        try:
            remotes = []
            for remote in self.repo.remotes:
                remote_info = {
                    'name': remote.name,
                    'url': remote.url
                }
                remotes.append(remote_info)
                
            return remotes
            
        except Exception as e:
            self.logger.error(f"Failed to list remotes: {e}")
            return []
            
    def fetch(self, remote_name: str = "origin") -> bool:
        """
        Fetch from a remote repository.
        
        Args:
            remote_name: Name of the remote to fetch from
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            remote = self.repo.remotes[remote_name]
            remote.fetch()
            self.logger.info(f"Fetched from remote '{remote_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to fetch: {e}")
            return False
            
    def pull(self, remote_name: str = "origin", branch_name: str = None) -> bool:
        """
        Pull from a remote repository.
        
        Args:
            remote_name: Name of the remote to pull from
            branch_name: Name of the branch to pull (default: current)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            remote = self.repo.remotes[remote_name]
            if branch_name:
                remote.pull(branch_name)
            else:
                remote.pull()
                
            self.logger.info(f"Pulled from remote '{remote_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to pull: {e}")
            return False
            
    def push(self, remote_name: str = "origin", branch_name: str = None) -> bool:
        """
        Push to a remote repository.
        
        Args:
            remote_name: Name of the remote to push to
            branch_name: Name of the branch to push (default: current)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            remote = self.repo.remotes[remote_name]
            if branch_name:
                remote.push(branch_name)
            else:
                remote.push()
                
            self.logger.info(f"Pushed to remote '{remote_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to push: {e}")
            return False
            
    def create_stash(self, message: str = None) -> bool:
        """
        Create a stash of current changes.
        
        Args:
            message: Stash message
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            if message:
                self.repo.git.stash('push', '-m', message)
            else:
                self.repo.git.stash('push')
                
            self.logger.info("Changes stashed")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create stash: {e}")
            return False
            
    def list_stashes(self) -> List[Dict[str, Any]]:
        """
        List all stashes.
        
        Returns:
            List of stash information
        """
        if not self.is_repository():
            return []
            
        try:
            stashes = []
            for stash in self.repo.git.stash('list').split('\n'):
                if stash:
                    # Parse stash information
                    parts = stash.split(':')
                    if len(parts) >= 2:
                        stash_info = {
                            'id': parts[0].strip(),
                            'description': parts[1].strip()
                        }
                        stashes.append(stash_info)
                        
            return stashes
            
        except Exception as e:
            self.logger.error(f"Failed to list stashes: {e}")
            return []
            
    def apply_stash(self, stash_id: str = "0") -> bool:
        """
        Apply a stash.
        
        Args:
            stash_id: ID of the stash to apply
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            self.repo.git.stash('apply', stash_id)
            self.logger.info(f"Applied stash {stash_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply stash: {e}")
            return False
            
    def get_diff(self, file_path: str = None, staged: bool = False) -> str:
        """
        Get diff information.
        
        Args:
            file_path: Path to specific file (None for all)
            staged: Whether to show staged changes
            
        Returns:
            Diff output as string
        """
        if not self.is_repository():
            return "Not a Git repository"
            
        try:
            if staged:
                if file_path:
                    diff = self.repo.git.diff('--cached', file_path)
                else:
                    diff = self.repo.git.diff('--cached')
            else:
                if file_path:
                    diff = self.repo.git.diff(file_path)
                else:
                    diff = self.repo.git.diff()
                    
            return diff if diff else "No changes"
            
        except Exception as e:
            self.logger.error(f"Failed to get diff: {e}")
            return f"Error getting diff: {e}"
            
    def reset_file(self, file_path: str) -> bool:
        """
        Reset a file to HEAD.
        
        Args:
            file_path: Path to the file to reset
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            self.repo.git.checkout('HEAD', '--', file_path)
            self.logger.info(f"Reset file: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reset file: {e}")
            return False
            
    def create_backup_branch(self, backup_name: str = None) -> bool:
        """
        Create a backup branch of current state.
        
        Args:
            backup_name: Name for the backup branch
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_repository():
            self.logger.error("Not a Git repository")
            return False
            
        try:
            if not backup_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"backup_{timestamp}"
                
            # Create backup branch
            backup_branch = self.repo.create_head(backup_name)
            self.logger.info(f"Created backup branch: {backup_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create backup branch: {e}")
            return False


class ProjectVersionControl:
    """
    High-level version control interface for projects.
    """
    
    def __init__(self, project_path: str):
        """
        Initialize project version control.
        
        Args:
            project_path: Path to the project
        """
        self.git_integration = GitIntegration(project_path)
        self.project_path = project_path
        
    def initialize_project(self, author_name: str, author_email: str) -> bool:
        """
        Initialize version control for a new project.
        
        Args:
            author_name: Author name
            author_email: Author email
            
        Returns:
            True if successful, False otherwise
        """
        if not self.git_integration.is_repository():
            return False
            
        try:
            # Configure user
            self.git_integration.repo.config_writer().set_value("user", "name", author_name)
            self.git_integration.repo.config_writer().set_value("user", "email", author_email)
            
            # Create initial commit
            self.git_integration.add_files()
            self.git_integration.commit("Initial project setup")
            
            # Create main branch
            if 'main' not in [b.name for b in self.git_integration.repo.branches]:
                self.git_integration.create_branch('main')
                self.git_integration.checkout_branch('main')
                
            # Create development branch
            self.git_integration.create_branch('develop')
            
            # Create initial tag
            self.git_integration.create_tag('v0.1.0', 'Initial version')
            
            return True
            
        except Exception as e:
            self.git_integration.logger.error(f"Failed to initialize project: {e}")
            return False
            
    def get_project_info(self) -> Dict[str, Any]:
        """
        Get comprehensive project information.
        
        Returns:
            Project information dictionary
        """
        info = {
            'path': self.project_path,
            'name': os.path.basename(self.project_path),
            'git_status': self.git_integration.get_status(),
            'branches': self.git_integration.list_branches(),
            'tags': self.git_integration.list_tags(),
            'remotes': self.git_integration.list_remotes(),
            'recent_commits': self.git_integration.get_commit_history(10)
        }
        
        return info
        
    def create_feature_branch(self, feature_name: str) -> bool:
        """
        Create a feature branch for development.
        
        Args:
            feature_name: Name of the feature
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure we're on develop branch
            if self.git_integration.repo.active_branch.name != 'develop':
                self.git_integration.checkout_branch('develop')
                self.git_integration.pull()
                
            # Create feature branch
            branch_name = f"feature/{feature_name}"
            return self.git_integration.create_branch(branch_name)
            
        except Exception as e:
            self.git_integration.logger.error(f"Failed to create feature branch: {e}")
            return False
            
    def finish_feature(self, feature_name: str, commit_message: str) -> bool:
        """
        Finish a feature by merging it back to develop.
        
        Args:
            feature_name: Name of the feature
            commit_message: Commit message for the merge
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Switch to develop branch
            self.git_integration.checkout_branch('develop')
            
            # Merge feature branch
            branch_name = f"feature/{feature_name}"
            success = self.git_integration.merge_branch(branch_name)
            
            if success:
                # Delete feature branch
                self.git_integration.delete_branch(branch_name)
                
            return success
            
        except Exception as e:
            self.git_integration.logger.error(f"Failed to finish feature: {e}")
            return False
            
    def create_release(self, version: str, release_notes: str = None) -> bool:
        """
        Create a release by merging develop to main.
        
        Args:
            version: Version number (e.g., "1.0.0")
            release_notes: Release notes
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Switch to main branch
            self.git_integration.checkout_branch('main')
            
            # Pull latest changes
            self.git_integration.pull()
            
            # Merge develop branch
            success = self.git_integration.merge_branch('develop')
            
            if success:
                # Create version tag
                tag_message = f"Release {version}"
                if release_notes:
                    tag_message += f"\n\n{release_notes}"
                    
                self.git_integration.create_tag(f"v{version}", tag_message)
                
                # Push to remote
                self.git_integration.push()
                
            return success
            
        except Exception as e:
            self.git_integration.logger.error(f"Failed to create release: {e}")
            return False


def main():
    """Main function to demonstrate Git integration."""
    try:
        # Example usage
        project_path = "~/test_hydrology_project"
        
        # Initialize version control
        vc = ProjectVersionControl(project_path)
        
        # Initialize project
        if vc.initialize_project("John Doe", "john.doe@example.com"):
            print("Project initialized successfully")
            
            # Get project info
            info = vc.get_project_info()
            print(f"Project: {info['name']}")
            print(f"Current branch: {info['git_status']['branch']}")
            print(f"Branches: {[b['name'] for b in info['branches']]}")
            
            # Create feature branch
            if vc.create_feature_branch("new-simulation-model"):
                print("Feature branch created")
                
        else:
            print("Failed to initialize project")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
