# Put the complete project in GitHub

Unzip `Anatomy_Evidence_Lab_GitHub.zip`. Open the inner `anatomy-evidence-lab` folder. That folder contains `package.json`, `.github`, `.gitignore`, the source and lecture files.

## GitHub Desktop (simple path)

1. Install GitHub Desktop and sign in.
2. Choose **File → Add local repository** and select this folder.
3. If Desktop says it is not a Git repository, use its **create a repository here** link. Keep this exact folder as the repository root. Do not initialize a second nested project folder or overwrite the provided README.
4. Review the file list. `.github/` and `.gitignore` must be present. `node_modules`, `dist`, `.dev.vars`, `.env` and API keys must be absent.
5. Commit with a message such as `Initial anatomy review project`.
6. Click **Publish repository**, use `anatomy-evidence-lab` as the name, and select **Keep this code private**.
7. Invite teammates through GitHub repository **Settings → Collaborators** if needed.

Use Desktop's **Fetch/Pull** before editing and **Commit → Push origin** after changes. Keep all project files together; GitHub's browser uploader can omit hidden configuration folders, so Desktop is preferable for this package.

## Terminal alternative

Create an **empty private** GitHub repository without adding a README or license. Open a terminal in this project's root:

```sh
git init -b main
git add .
git commit -m "Initial anatomy review project"
git remote add origin https://github.com/YOUR_USERNAME/anatomy-evidence-lab.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. Authenticate using GitHub's normal sign-in/credential manager; do not put a token in the remote URL.

## Enable deployments after setup

Follow [DEPLOYMENT.md](DEPLOYMENT.md) to create your Cloudflare database and first private deployment. Then add the two GitHub secrets and deployment variable described there. From then on, pushing to `main` runs the build and deploys the updated website.

## Work safely with teammates

Make a branch for each change, open a pull request, and merge after the checks pass. Add branch protection for `main` when the team starts collaborating. Tags such as `demo-review-v1` give you identifiable checkpoints for client demos.
