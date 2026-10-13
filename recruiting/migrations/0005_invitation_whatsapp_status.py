from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recruiting", "0004_candidate_education_records_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="whatsapp_status",
            field=models.CharField(default="not configured", max_length=20),
        ),
    ]
