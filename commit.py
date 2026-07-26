import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from huggingface_hub import HfApi
from dotenv import load_dotenv

# ================= 配置区域 =================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / "token.env")

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise ValueError("未找到 HF_TOKEN, 请检查 .env 文件！")

# Hugging Face 配置
HF_REPO_ID = "xiaobukeai/personal_mainpage"

# GitHub 配置
GITHUB_REPO = "xiaobukeaimiao/xiaobukeaimiao.github.io"
MAIN_BRANCH = "main"

# 本地目录配置
FILES_DIR = BASE_DIR / "files"
# ============================================

def upload_to_huggingface():
    """使用 huggingface_hub 将 files 目录全量/增量同步至 Hugging Face"""
    if not FILES_DIR.exists() or not any(FILES_DIR.iterdir()):
        print("未检测到 files 目录或目录为空，跳过 Hugging Face 同步。")
        return True

    print(">>> [Phase 1] 开始同步文件到 Hugging Face 数据集...")
    api = HfApi(token=HF_TOKEN)

    try:
        print(f"  └─ 正在对比并增量上传 '{FILES_DIR.name}' 到 {HF_REPO_ID} ...")
        api.upload_folder(
            folder_path=str(FILES_DIR),
            path_in_repo="files",
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            commit_message=f"Sync assets at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print("✅ Hugging Face 资源同步完成！")
        return True
    except Exception as e:
        print(f"❌ Hugging Face 上传失败: {e}")
        return False

def main():
    os.chdir(BASE_DIR)

    # 1. 上传所有大文件/媒体文件至 Hugging Face
    if not upload_to_huggingface():
        print("⛔ 部署流程终止。")
        return

    # 2. 准备处理本地 Markdown 文件
    md_files = list(BASE_DIR.glob("*.md"))
    if not md_files:
        print("未找到 Markdown 文件，部署结束。")
        return

    print("\n>>> [Phase 2] 开始处理 Markdown 并推送到 GitHub...")
    
    files_to_replace = []
    if FILES_DIR.exists():
        files_to_replace = [p.relative_to(BASE_DIR).as_posix() for p in FILES_DIR.rglob("*") if p.is_file()]

    bak_files_created = []
    hf_base_url = f"https://huggingface.co/datasets/{HF_REPO_ID}/resolve/main/"

    try:
        # 步骤 1：保存本地原始 Markdown
        subprocess.run(['git', 'add'] + [str(p) for p in md_files], check=True, capture_output=True)
        
        has_staged_changes = subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0
        if has_staged_changes:
            subprocess.run(['git', 'commit', '-m', "Save local source files"], check=True, capture_output=True)

        print("正在将 Markdown 相对路径临时替换为 Hugging Face 媒体直链...")

        # 步骤 2：备份并使用占位符安全替换
        token_map = {}
        for idx, local_path in enumerate(sorted(files_to_replace, key=len, reverse=True)):
            token = f"___CDN_PLACEHOLDER_{idx}___"
            dl_url = f"{hf_base_url}{local_path}"
            token_map[token] = dl_url

        for md_path in md_files:
            md_str = str(md_path)
            bak_str = f"{md_str}.bak"
            shutil.copy2(md_str, bak_str)
            bak_files_created.append((bak_str, md_str))
            
            with open(md_str, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            # 先转占位符
            for token, dl_url in token_map.items():
                local_p = dl_url.replace(hf_base_url, "")
                new_content = new_content.replace(f"./{local_p}", token)
                new_content = new_content.replace(local_p, token)
            
            # 再统一转 CDN 直链
            for token, dl_url in token_map.items():
                new_content = new_content.replace(token, dl_url)
                
            with open(md_str, 'w', encoding='utf-8') as f:
                f.write(new_content)

        # 步骤 3：提交带网络直链的 Markdown 并推送到 GitHub
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        
        has_replaced_changes = subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0
        if has_replaced_changes:
            commit_msg = f"Deploy updates at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
            print(f"正在推送到 GitHub {MAIN_BRANCH} 分支...")
            # 将原本的 push 命令加上 '-f' 强制覆盖远程分支
            subprocess.run(['git', 'push', '-f', 'origin', MAIN_BRANCH], check=True)

            subprocess.run(['git', 'reset', '--hard', 'HEAD~1'], check=True, capture_output=True)
            print("✅ 成功推送带正确 CDN 链接的 Markdown 到 GitHub！")
        else:
            print("  └─ Markdown 页面无变动，无需推送 GitHub。")

    except Exception as e:
        print(f"❌ 部署过程发生错误: {e}")

    finally:
        # 步骤 5：还原本地 Markdown 文件的相对路径
        print("\n>>> [Phase 3] 正在还原本地 Markdown 文件环境...")
        for bak_str, md_str in bak_files_created:
            if os.path.exists(bak_str):
                shutil.move(bak_str, md_str) 
        print("🎉 部署流程结束！")

if __name__ == "__main__":
    main()