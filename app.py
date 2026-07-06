import io
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import openai
import pymupdf
from openai import OpenAI
from pypdf import PdfReader

try:  # OCR is optional; the app still runs for text/digital PDFs without it.
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover
    RapidOCR = None

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload cap

MIN_TEXT_LENGTH = 20  # below this, treat a PDF as scanned/image-based
MAX_OCR_PAGES = 15    # cap pages we OCR so a huge scan can't hang the request
OCR_DPI = 130         # legible for OCR while keeping rendering fast

_ocr_engine = None


def _get_ocr():
    """Lazily build a single shared OCR engine (model load is slow)."""
    global _ocr_engine
    if _ocr_engine is None:
        if RapidOCR is None:
            raise RuntimeError("OCR engine (rapidocr-onnxruntime) is not installed")
        _ocr_engine = RapidOCR()
    return _ocr_engine

SYSTEM_PROMPT = """You are the IEP Explainer, a warm, knowledgeable special-education navigator. You help parents and guardians understand their child's Individualized Education Program (IEP) — a dense, jargon-heavy document schools produce — so they can walk into their next meeting informed and confident. You are not a lawyer and not a substitute for professional advocacy; you help them prepare.

You will be given the text of an IEP (or part of one). Work ONLY from the text provided — never invent content that isn't there. If key sections appear to be missing from the text, say so rather than assuming.

Reply in the same language as the document (English or Spanish). Structure your ENTIRE response as exactly these three markdown sections, using these headings verbatim and in this order:

## Plain-Language Summary
Explain, in warm plain language a busy parent can understand, what this IEP actually says: the child's present levels of performance, the annual goals (what the school is aiming for and how progress is measured), the services and how often they happen, and the accommodations or modifications. Define jargon in parentheses the first time it appears (e.g. "FAPE (a free appropriate public education)"). Use short bullet points.

## Possible Gaps & Missing Pieces
Point out things a strong IEP usually includes that look weak, vague, or absent in this text — for example: goals that aren't measurable, present levels stated without data, services with no frequency/duration/location, accommodations not tied to a stated need, no progress-monitoring method, or (for older students) a missing transition plan. Frame each as something to look into, not a definitive legal judgment. Only flag what you can actually tell from the provided text.

## Questions to Bring to the Meeting
Give 4-7 specific, respectful, empowering questions the parent can ask the IEP team, drawn from the gaps above and the child's stated needs. Use a bullet list.

After the third section, add one brief encouraging sentence. Keep the whole thing scannable. Do not add any sections or headings beyond the three above."""


@app.route("/")
def index():
    return render_template("index.html")


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "That file is too large (max 16 MB)."}), 413


def _ocr_pdf(file_bytes):
    """Render a scanned PDF's pages and OCR them into plain text.

    Used when a PDF has no embedded text layer (a scan or photo). Reading the
    text locally and feeding it to the model — instead of sending page images
    to a vision model — is reliable and never triggers image-safety refusals.
    """
    engine = _get_ocr()

    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    images = []
    for page in doc[:MAX_OCR_PAGES]:
        pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        ).copy()
        images.append(img)
    doc.close()

    def run(img):
        result, _ = engine(img)
        return " ".join(line[1] for line in result) if result else ""

    # onnxruntime releases the GIL during inference, so OCR pages in parallel.
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages_text = list(pool.map(run, images))

    return "\n\n".join(t for t in pages_text if t).strip()


@app.route("/api/explain", methods=["POST"])
def explain():
    text = (request.form.get("text") or "").strip()
    file = request.files.get("document")

    if file and file.filename:
        filename = file.filename.lower()
        if filename.endswith(".pdf"):
            file_bytes = file.read()
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                app.logger.error("Error parsing PDF: %s", e)
                return jsonify({
                    "error": "Sorry, I couldn't read that PDF. Try pasting the text instead."
                }), 400

            text = (text or "").strip()

            if len(text) < MIN_TEXT_LENGTH:
                # No text layer — a scan or photo. OCR the pages into text.
                try:
                    text = _ocr_pdf(file_bytes)
                except Exception as e:
                    app.logger.error("Error running OCR on PDF: %s", e)
                    return jsonify({
                        "error": "Sorry, I couldn't read text from that PDF. "
                                 "Please try pasting the text instead."
                    }), 400

                if len(text.strip()) < MIN_TEXT_LENGTH:
                    return jsonify({
                        "error": "We received your PDF but couldn't read any text from it. "
                                 "It may be a very low-quality scan — please try pasting the text instead."
                    }), 400
        elif filename.endswith(".txt"):
            text = file.read().decode("utf-8", errors="ignore")
        else:
            return jsonify({"error": "Please upload a PDF or .txt file."}), 400

    text = (text or "").strip()

    if not text:
        return jsonify({
            "error": "Please paste your IEP text or upload the document first."
        }), 400

    if not os.environ.get("OPENAI_API_KEY"):
        app.logger.error("OPENAI_API_KEY is not set")
        return jsonify({
            "error": "The server's OPENAI_API_KEY is missing. Please contact the site administrator."
        }), 500

    if len(text) > 50000:
        text = text[:50000]

    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        result_text = response.choices[0].message.content or ""
        return jsonify({"result": result_text})

    except openai.AuthenticationError as e:
        app.logger.error("OpenAI authentication error: %s", e)
        return jsonify({
            "error": "The server's OPENAI_API_KEY is missing or invalid. Please contact the site administrator."
        }), 500

    except Exception as e:
        app.logger.error("Error calling OpenAI API: %s", e)
        return jsonify({
            "error": "Something went wrong while explaining your IEP. Please try again in a moment."
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
