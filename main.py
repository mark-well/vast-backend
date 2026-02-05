
import pdfplumber
import os
import json

# Extract from a pdf file
def extract_text_from_pdf(pdf):
    with pdfplumber.open(pdf) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(
            use_text_flow = True,
            keep_blank_chars = False
        )

    for w in words:
        print(w)

# Extract a block of text from pdf
def extract_block_of_text_from_pdf(pdf):
    blocks=[]
    with pdfplumber.open(pdf) as pdf:
        for page in pdf.pages:
            for line in page.extract_text_lines():
                blocks.append({
                    "text": line["text"],
                    "top": line["top"],
                    "size": line["chars"][0]["size"]
                })
    return blocks

def chunk_blocks(blocks, max_char=1000):
    chunks = []
    current = ""

    for block in blocks:
        if len(current) + len(block["text"]) > max_char:
            chunks.append(current)
            current = ""
        current += block["text"] + "\n"

    if current:
        chunks.append(current)
    return chunks

def create_output_file(file_name):
    if not os.path.exists(file_name):
        open(file_name, "x")

# extract blocks of text then save to a file (for debugging only)
def extract_block_text_save_to_file():
    file_name = "blocks.json"
    blocks = extract_block_of_text_from_pdf("sample.pdf")
    create_output_file(file_name)

    with open(file_name, "w") as f:
        for block in blocks:
            f.write(json.dumps(block))
            f.write("\n")

def main():
    # extract_text_from_pdf("sample.pdf")
    # extract_block_text_save_to_file()
    blocks = extract_block_of_text_from_pdf("sample.pdf")
    chunks = chunk_blocks(blocks)
    for chunk in chunks:
        print(chunk)
        print("\n")

if __name__ == "__main__":
    main()