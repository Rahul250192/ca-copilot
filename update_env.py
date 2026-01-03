import os

env_path = "/Users/rahulgupta/ca-copilot/.env"
db_url = "postgresql://cacopilot_db_user:tUv90E1G2QZq2MbsFm6AWhsCUDIBDD9Q@dpg-d5bnm8qli9vc73brh100-a.singapore-postgres.render.com/cacopilot_db"

# Read existing lines
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        lines = f.readlines()
else:
    lines = []

# Update or Append
found = False
new_lines = []
for line in lines:
    if line.startswith("DATABASE_URL="):
        new_lines.append(f"DATABASE_URL={db_url}\n")
        found = True
    else:
        new_lines.append(line)

if not found:
    new_lines.append(f"DATABASE_URL={db_url}\n")

with open(env_path, "w") as f:
    f.writelines(new_lines)

print("Updated .env successfully.")
