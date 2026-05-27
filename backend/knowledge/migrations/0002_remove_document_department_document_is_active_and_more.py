# Manual migration - applied manually due to data type conversion
# department removed, is_active added, category_l1/l2 changed to FK (bigint)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0001_initial"),
        ("tags", "0001_initial"),
    ]

    operations = [
        # All changes applied manually via SQL:
        # - Removed department varchar column
        # - Added is_active bool column
        # - Changed category_l1 varchar -> category_l1_id bigint FK -> tags_tag
        # - Changed category_l2 varchar -> category_l2_id bigint FK -> tags_tag
        migrations.RemoveField(
            model_name="document",
            name="department",
        ),
        migrations.AddField(
            model_name="document",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="激活状态"),
        ),
        migrations.AlterField(
            model_name="document",
            name="category_l1",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="documents_l1",
                to="tags.tag",
                verbose_name="一级分类",
                db_column="category_l1_id",
            ),
        ),
        migrations.AlterField(
            model_name="document",
            name="category_l2",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="documents_l2",
                to="tags.tag",
                verbose_name="二级分类",
                db_column="category_l2_id",
            ),
        ),
    ]
