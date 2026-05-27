"""清理过期的 AI 生成文件"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from chat.models import GeneratedFile


class Command(BaseCommand):
    help = "清理过期的 AI 生成文件（从 MinIO 和数据库中删除）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="删除多少天前创建的文件（默认 30 天）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只打印将被删除的文件，不实际删除",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        # 查找过期文件：有 expires_at 且已过期，或超过 days 天
        expired = GeneratedFile.objects.filter(
            created_at__lt=cutoff,
        )

        count = expired.count()
        if count == 0:
            self.stdout.write("没有需要清理的文件")
            return

        if dry_run:
            for f in expired[:20]:
                self.stdout.write(f"  [DRY] {f.file_name} ({f.file_size} bytes, {f.created_at})")
            self.stdout.write(f"共 {count} 个文件将被删除（dry-run 模式）")
            return

        # 实际删除
        deleted = 0
        for f in expired:
            try:
                from knowledge.minio_client import get_minio_client

                client = get_minio_client()
                parts = f.minio_path.split("/", 1)
                if len(parts) == 2:
                    client.remove_object(parts[0], parts[1])
            except Exception as e:
                self.stderr.write(f"MinIO 删除失败 {f.minio_path}: {e}")

            f.delete()
            deleted += 1

        self.stdout.write(self.style.SUCCESS(f"已清理 {deleted} 个过期文件"))
