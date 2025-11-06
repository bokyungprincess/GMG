import fitz

doc = fitz.open("최유리-숲.pdf")
for i, page in enumerate(doc):
    img = page.get_pixmap()
    img.save(f"music{i}.jpg")