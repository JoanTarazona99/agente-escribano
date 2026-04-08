# Generated migration for file upload support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('articles', '0007_add_ai_processing_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='source_db',
            field=models.CharField(
                choices=[
                    ('scopus', 'Scopus'),
                    ('wos', 'Web of Science'),
                    ('arxiv', 'arXiv'),
                    ('elibrary', 'eLIBRARY'),
                    ('file', 'Archivo local'),
                    ('unknown', 'Desconocido'),
                ],
                default='unknown',
                max_length=20,
                verbose_name='Base de datos fuente',
            ),
        ),
        migrations.AddField(
            model_name='article',
            name='full_text',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Texto completo extraído del archivo subido (PDF, TXT, DOCX).',
                verbose_name='Texto completo',
            ),
        ),
        migrations.AddField(
            model_name='article',
            name='original_filename',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Nombre del archivo subido por el usuario.',
                max_length=512,
                verbose_name='Nombre del archivo original',
            ),
        ),
    ]
