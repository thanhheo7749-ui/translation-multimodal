# Publish this project to GitHub

Target: https://github.com/thanhheo7749-ui/translation-multimodal.git

Run from your Windows terminal with Git for Windows installed and access to that repository:

```powershell
.\publish_project.cmd -ValidateOnly
.\publish_project.cmd
```

Git/Git Credential Manager handles authentication interactively. If Git reports a missing author identity, configure your own Git name and email, then rerun. The script does not save credentials or configure an identity.

Each run clones into a unique `.publish-staging` directory and creates an `import/translation-project-...` branch from the remote default branch. An empty repository gets a new initial import branch. It copies and commits the selected project files, then pushes only that new branch. Existing remote files remain; imported paths may be updated on the new branch. Existing `.gitignore` rules are preserved and extended. There is no force push, default-branch update, merge, or deletion. The terminal prints the exact branch and commit after a successful push.

The import includes text source/configuration files from `backend`, `frontend`, `tests`, `scripts`, `docs`, `research`, and `experiments`, plus the root launchers, network diagnostic helpers, project plan, publishing launcher, and `.gitignore`. It excludes environments, caches, runtime logs/results directories, downloaded models/media, binary documents, agent installations, vendor repositories, and all `data` files. Annotation datasets can be reviewed and added separately later.

Files selected for import are checked before cloning and after copying. Credential-like filenames, common credential patterns, private keys, symbolic links, and text files over 20 MB fail the run without printing matched secrets. This is a conservative preflight, not a guarantee that all sensitive information can be detected. Inspect the import branch before merging or changing repository visibility.

On errors, the original project and any created import checkout are retained. A failed push can leave a local commit in the printed staging path; a fresh run creates another isolated branch. No network or authentication operation occurs with `-ValidateOnly`.
