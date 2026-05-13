from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('testapp', '0005_alter_configuredform_options_formnotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='formstep',
            name='back_label',
            field=models.CharField(blank=True, max_length=200, verbose_name='back label'),
        ),
        migrations.AddField(
            model_name='formstep',
            name='next_label',
            field=models.CharField(blank=True, max_length=200, verbose_name='next label'),
        ),
    ]
