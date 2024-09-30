import git
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Repository details
repo_name = "CaptureCompare"
repo_description = "Streamlit app for CaptureCompare"
github_username = "korm85"
personal_access_token = "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"

# Set the path to your Streamlit app
repo_path = r"C:\Users\korenevskym\OneDrive - 3D Systems\Documents\CaptureCompare"

try:
    # Initialize the repository if it's not already a Git repository
    try:
        git_repo = git.Repo(repo_path)
        logging.info(f"Opened existing Git repository in {repo_path}")
    except git.exc.InvalidGitRepositoryError:
        git_repo = git.Repo.init(repo_path)
        logging.info(f"Initialized new Git repository in {repo_path}")

    # Change to the repository directory
    os.chdir(repo_path)
    logging.info(f"Changed working directory to {repo_path}")

    # Create a README file if it doesn't exist
    readme_path = os.path.join(repo_path, "README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write(f"# {repo_name}\n\n{repo_description}")
        logging.info("Created README.md file")

    # Add all files to the repository
    git_repo.git.add(A=True)
    logging.info("Added all files to the repository")

    # Commit changes if there are any
    if git_repo.is_dirty() or len(git_repo.untracked_files) > 0:
        git_repo.index.commit("Update repository")
        logging.info("Committed changes to local repository")

    # Set up the remote repository
    remote_url = f"https://{personal_access_token}@github.com/{github_username}/{repo_name}.git"
    try:
        origin = git_repo.remote("origin")
        if origin.url != remote_url:
            origin.set_url(remote_url)
            logging.info("Updated remote URL")
        else:
            logging.info("Remote 'origin' already exists with correct URL")
    except git.exc.NoSuchPathError:
        logging.info("Remote 'origin' not found. Creating new remote.")
        origin = git_repo.create_remote("origin", url=remote_url)
        logging.info("Created new 'origin' remote")

    # Verify remote creation
    if "origin" not in git_repo.remotes:
        raise git.exc.GitCommandError("create_remote", "Failed to create 'origin' remote")

    # Push changes to the remote repository
    branch_name = "master" if "master" in git_repo.heads else "main"
    origin.push(branch_name)
    logging.info(f"Pushed changes to {branch_name} branch on GitHub")

    logging.info(f"Repository '{repo_name}' has been successfully updated and pushed to GitHub.")

except git.exc.GitCommandError as e:
    logging.error(f"Git command error: {e}")
    if "not found" in str(e):
        logging.error(f"The repository '{repo_name}' doesn't exist on GitHub.")
        logging.error("Please create the repository on GitHub first, then run this script again.")
    elif "remote origin already exists" in str(e):
        logging.error("Remote 'origin' already exists. This might be due to a configuration issue.")
        logging.info("Attempting to update the existing remote...")
        git_repo.delete_remote("origin")
        git_repo.create_remote("origin", url=remote_url)
        logging.info("Remote 'origin' has been updated. Please run the script again.")
except Exception as e:
    logging.error(f"An unexpected error occurred: {e}")

logging.info("Script execution completed.")