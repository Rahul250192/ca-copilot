# Zero-Touch Deployment Guide (Render) 🚀

This guide explains how to deploy CA-Copilot to **Render** with complete automation. Every `git push` will now automatically update your server.

## 1. Prerequisites (Do this ONCE)
1.  **Create a Free Supabase Project**:
    - Go to [Supabase](https://supabase.com/) and create a new project.
    - Go to **Project Settings > Database** and copy the **Connection String** (URI).
    - It should look like: `postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres`
2.  **Enable Supabase Storage**:
    - Go to **Storage** in the left sidebar.
    - Click **New Bucket** and name it `knowledge-kits`.
    - Set the bucket to **Public** (or add a policy to allow the backend to read/write).
    - Get your **Project URL** and **Service Role Key** from **Settings > API**.

## 2. One-Click Deployment on Render
1.  Go to **[Render Dashboard](https://dashboard.render.com/)**.
2.  Click **New > Blueprint**.
3.  Connect your GitHub repository: `Rahul250192/ca-copilot`.
4.  Render will automatically see the `render.yaml` file.
5.  It will ask you for 2 values:
    - **DATABASE_URL**: Paste your Supabase URI (Ensure you use `postgresql://` and not `postgres://`).
    - **OPENAI_API_KEY**: Paste your OpenAI key.
6.  Click **Apply**.

## 3. What happens automatically?
Once you click apply, Render handles everything:
- **Builds Docker**: It installs Python and all dependencies.
- **Auto-Migrate**: It creates your DB tables using Alembic.
- **Auto-Seed**: It creates the default Kits (GST, Audit, etc.).
- **Auto-Update**: Every time you push code to GitHub, Render will redeploy the new version automatically.

---
**Your API is now live!** No terminal commands or manual setup required on the server.
