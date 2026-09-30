from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("resumes", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="is_active",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="verification_code",
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="verification_code_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
