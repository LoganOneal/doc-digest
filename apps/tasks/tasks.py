import os
from apps import db, grobid_client
from flask_login import current_user
from apps.tasks import celery
from apps.grobid_client.api.pdf import process_fulltext_document
from apps.models import File, ArticleModel, Section, Paragraph
from apps.grobid_client.models import Article, ProcessForm
from apps.grobid_client.types import TEI, File, UNSET
import time 

BASE_TEMP_DIR = 'temp'

@celery.task
def parse_task(file_id) -> Article:
    print("PARSE TASK!!")

    file = File.query.filter_by(id=file_id).first()

    print("File: ", file.filename)

    if file.extension != 'pdf':
        print('File is not a PDF!')
        return None

    os.makedirs(BASE_TEMP_DIR, exist_ok=True)
    pdf_file = os.path.join(BASE_TEMP_DIR, f'{file.id}.pdf')

    with open(pdf_file, "wb") as f:
        f.write(file.data)

    with open(pdf_file,"rb") as fin:
        form = ProcessForm(
            segment_sentences="0",
            input_=File(file_name=file.filename, payload=fin, mime_type="application/pdf"),
        )
        r = process_fulltext_document.sync_detailed(client=grobid_client, multipart_data=form)

        if r.is_success:
            article: Article = TEI.parse(r.content, figures=False)
            assert article.title
        else:
            print("Error: failed to parse file")

    os.remove(pdf_file)

    article_model = ArticleModel(title=article.title,user_id=current_user.get_id())
    db.session.add(article_model)

    for section in article.sections:
        name = None
        num = None
        if section.name is not UNSET:
            name = section.name
        if section.num is not UNSET:
            num = section.num

        section_model = Section(name=name, num=num)
        article_model.sections.append(section_model)
        db.session.add(section_model)

        for paragraph in section.paragraphs:
            paragraph_model = Paragraph(text=paragraph.text)
            section_model.paragraphs.append(paragraph_model)
            db.session.add(paragraph_model)
    
        db.session.commit() 

    return article