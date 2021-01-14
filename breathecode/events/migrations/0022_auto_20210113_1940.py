# Generated by Django 3.1.4 on 2021-01-13 19:40

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0021_auto_20210111_2030'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventcheckin',
            name='attendee',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]
