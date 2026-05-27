"""迁移 MinIO 旧桶数据到新桶

将 knowledge-base 桶中的 ppt-output/ 和 agent-upload/ 前缀对象
分别迁移到 generated-files 和 chat-uploads 独立桶，并更新数据库记录。

用法：
    python manage.py migrate_minio_buckets --dry-run    # 预览模式
    python manage.py migrate_minio_buckets              # 执行迁移
"""
from django.core.management.base import BaseCommand
from minio.commonconfig import CopySource

from chat.models import GeneratedFile, MessageAttachment
from knowledge.minio_client import get_minio_client, ensure_bucket


OLD_PPT_PREFIX = "knowledge-base/ppt-output/"
OLD_UPLOAD_PREFIX = "knowledge-base/agent-upload/"

NEW_GEN_BUCKET = "generated-files"
NEW_UPLOAD_BUCKET = "chat-uploads"

OLD_BUCKET = "knowledge-base"


class Command(BaseCommand):
    help = "迁移 MinIO 旧桶数据到新桶（ppt-output → generated-files, agent-upload → chat-uploads）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只打印迁移计划，不实际执行",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        client = get_minio_client()

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY-RUN 模式 ===\n"))

        # ── 阶段 1：迁移 PPT 生成文件 ──
        self._migrate_generated_files(client, dry_run)

        # ── 阶段 2：迁移聊天上传文件 ──
        self._migrate_chat_uploads(client, dry_run)

        self.stdout.write(self.style.SUCCESS("\n迁移完成"))

    def _migrate_generated_files(self, client, dry_run: bool):
        self.stdout.write("\n── 阶段 1：迁移 GeneratedFile (PPT 等) ──")

        records = GeneratedFile.objects.filter(
            minio_path__startswith=OLD_PPT_PREFIX
        )
        total = records.count()
        self.stdout.write(f"需要迁移：{total} 条记录")

        if total == 0:
            return

        if not dry_run:
            ensure_bucket(NEW_GEN_BUCKET)

        migrated, failed = 0, 0
        for gf in records:
            old_path = gf.minio_path
            # knowledge-base/ppt-output/{uuid}.pptx → {uuid}.pptx
            object_name = old_path[len(OLD_PPT_PREFIX):]
            new_path = f"{NEW_GEN_BUCKET}/{object_name}"

            if dry_run:
                self.stdout.write(f"  [DRY] {old_path} → {new_path}")
                migrated += 1
                continue

            try:
                # 1. 复制到新桶
                source = CopySource(OLD_BUCKET, f"ppt-output/{object_name}")
                client.copy_object(NEW_GEN_BUCKET, object_name, source)

                # 2. 更新数据库
                gf.minio_path = new_path
                gf.save(update_fields=["minio_path"])

                # 3. 删除旧对象
                client.remove_object(OLD_BUCKET, f"ppt-output/{object_name}")

                migrated += 1
            except Exception as e:
                failed += 1
                self.stderr.write(f"  [FAIL] {old_path}: {e}")

        self.stdout.write(f"  结果：迁移 {migrated}，失败 {failed}")

    def _migrate_chat_uploads(self, client, dry_run: bool):
        self.stdout.write("\n── 阶段 2：迁移 MessageAttachment (聊天上传) ──")

        records = MessageAttachment.objects.filter(
            file_path_minio__startswith=OLD_UPLOAD_PREFIX
        )
        total = records.count()
        self.stdout.write(f"需要迁移：{total} 条记录")

        if total == 0:
            return

        if not dry_run:
            ensure_bucket(NEW_UPLOAD_BUCKET)

        migrated, failed = 0, 0
        for att in records:
            old_path = att.file_path_minio
            # knowledge-base/agent-upload/{name} → {name}
            object_name = old_path[len(OLD_UPLOAD_PREFIX):]
            new_path = f"{NEW_UPLOAD_BUCKET}/{object_name}"

            if dry_run:
                self.stdout.write(f"  [DRY] {old_path} → {new_path}")
                migrated += 1
                continue

            try:
                # 1. 复制到新桶
                source = CopySource(OLD_BUCKET, f"agent-upload/{object_name}")
                client.copy_object(NEW_UPLOAD_BUCKET, object_name, source)

                # 2. 更新数据库
                att.file_path_minio = new_path
                att.save(update_fields=["file_path_minio"])

                # 3. 删除旧对象
                client.remove_object(OLD_BUCKET, f"agent-upload/{object_name}")

                migrated += 1
            except Exception as e:
                failed += 1
                self.stderr.write(f"  [FAIL] {old_path}: {e}")

        self.stdout.write(f"  结果：迁移 {migrated}，失败 {failed}")
