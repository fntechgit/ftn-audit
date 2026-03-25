from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuditedThing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
            ],
            options={
                "app_label": "tests_test_app",
            },
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=50)),
            ],
            options={
                "app_label": "tests_test_app",
            },
        ),
        migrations.CreateModel(
            name="AuditedBasket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("tags", models.ManyToManyField(related_name="baskets", to="tests_test_app.tag")),
            ],
            options={
                "app_label": "tests_test_app",
            },
        ),
    ]
