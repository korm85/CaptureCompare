import git
import os

# Repository details
repo_name = "CaptureCompare"
repo_description = "Streamlit app for CaptureCompare"
github_username = "korm85"
personal_access_token = "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"

# Set the path to your Streamlit app
repo_path = r"C:\Users\korenevskym\OneDrive - 3D Systems\Documents\CaptureCompare"

# Initialize the repository if it's not already a Git repository
try:
    git_repo = git.Repo(repo_path)
except git.exc.InvalidGitRepositoryError:
    git_repo = git.Repo.init(repo_path)

# Change to the repository directory
os.chdir(repo_path)

# Create a README file if it doesn't exist
readme_path = os.path.join(repo_path, "README.md")
if not os.path.exists(readme_path):
    with open(readme_path, "w") as f:
        f.write(f"# {repo_name}\n\n{repo_description}")

# Add all files to the repository
git_repo.git.add(A=True)

# Commit changes if there are any
if git_repo.is_dirty() or len(git_repo.untracked_files) > 0:
    git_repo.index.commit("Update repository")

# Add the remote repository if it doesn't exist
remote_url = f"https://{personal_access_token}@github.com/{github_username}/{repo_name}.git"
try:
    origin = git_repo.remote("origin")
    if origin.url != remote_url:
        origin.set_url(remote_url)
except git.exc.NoSuchPathError:
    origin = git_repo.create_remote("origin", url=remote_url)

# Push changes to the remote repository
try:
    origin.push("master" if "master" in git_repo.heads else "main")
    print(f"Repository '{repo_name}' has been updated and pushed to GitHub.")
except git.exc.GitCommandError as e:
    if "not found" in str(e):
        print(f"Error: The repository '{repo_name}' doesn't exist on GitHub.")
        print("Please create the repository on GitHub first, then run this script again.")
    else:
        print(f"An error occurred: {e}")

print("Script execution completed.")