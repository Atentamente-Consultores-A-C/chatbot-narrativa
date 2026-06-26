"""
Ingestión de documentos a Supabase.

Tipos de documento soportados (columna doc_type en mapeo.csv):
  knowledge          — manuales, PDFs de cursos (contenido socioemocional)
  behavior_example   — instrucciones de comportamiento, prompts, reglas
  conversation_example — ejemplos de conversaciones (diálogo socrático, etc.)

Uso:
  python -m bot.rag.ingest                        # solo archivos nuevos
  python -m bot.rag.ingest --force                # reingestar todo
  python -m bot.rag.ingest --docs-dir ./documents --batch-size 25

Requiere: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY en .env
"""
import argparse
import csv
import hashlib
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langchain_community.document_loaders import PyPDFDirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from bot.db.client import get_supabase

EMBED_MODEL = "text-embedding-3-small"
VALID_DOC_TYPES = {"knowledge", "behavior_example", "conversation_example"}


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_meta_map(csv_path: Path) -> dict:
    if not csv_path.exists():
        print(f"⚠️  No se encontró {csv_path}. Se usará metadata vacía.")
        return {}
    meta = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            fname = (row.get("source_file") or "").strip()
            if not fname:
                continue
            module_raw = (row.get("module") or "").strip()
            doc_type = (row.get("doc_type") or "knowledge").strip()
            if doc_type not in VALID_DOC_TYPES:
                print(f"⚠️  doc_type desconocido '{doc_type}' en {fname}, usando 'knowledge'")
                doc_type = "knowledge"
            meta[fname] = {
                "course": (row.get("course") or "ALL").strip(),
                "module": int(module_raw) if module_raw.isdigit() else None,
                "doc_type": doc_type,
                "source_file": fname,
            }
    return meta


def get_ingested_files() -> set[str]:
    """Retorna los source_file que ya están en Supabase (por su file_hash en metadata)."""
    sb = get_supabase()
    result = sb.table("documents").select("metadata->>file_hash").execute()
    return {row["file_hash"] for row in (result.data or []) if row.get("file_hash")}


def delete_file_chunks(source_file: str) -> None:
    """Borra todos los chunks de un archivo (para reingestión forzada)."""
    sb = get_supabase()
    sb.table("documents").delete().filter(
        "metadata->>source_file", "eq", source_file
    ).execute()


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def load_txt_files(docs_path: Path) -> list:
    """Carga archivos .txt (para ejemplos de conversaciones y comportamiento)."""
    docs = []
    for txt_file in docs_path.glob("*.txt"):
        try:
            loader = TextLoader(str(txt_file), encoding="utf-8")
            docs.extend(loader.load())
        except Exception as e:
            print(f"   ⚠️  No se pudo cargar {txt_file.name}: {e}")
    return docs


def ingest(docs_dir: str = "documents", batch_size: int = 25, force: bool = False) -> None:
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Directorio no encontrado: {docs_path}")

    meta_map = load_meta_map(docs_path / "mapeo.csv")
    already_ingested = set() if force else get_ingested_files()

    # Cargar PDFs y TXTs
    print(f"📂 Escaneando documentos en {docs_path}...")
    pdf_docs = PyPDFDirectoryLoader(str(docs_path)).load()
    txt_docs = load_txt_files(docs_path)
    raw_docs = pdf_docs + txt_docs
    print(f"   {len(raw_docs)} páginas/archivos encontrados.")

    # Filtrar solo archivos nuevos y enriquecer metadata
    to_process = []
    skipped = 0
    for doc in raw_docs:
        fname = Path(doc.metadata.get("source", "")).name
        fpath = docs_path / fname
        fhash = file_hash(fpath) if fpath.exists() else ""

        if not force and fhash in already_ingested:
            skipped += 1
            continue

        if force and fname:
            delete_file_chunks(fname)

        extra = meta_map.get(fname, {
            "course": "ALL",
            "module": None,
            "doc_type": "knowledge",
            "source_file": fname,
        })
        doc.metadata.update({**extra, "file_hash": fhash})
        to_process.append(doc)

    print(f"   {skipped} archivos ya ingestados (omitidos).")
    print(f"   {len(to_process)} páginas nuevas a procesar.")

    if not to_process:
        print("✅ Base de conocimiento al día, nada que ingestar.")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = splitter.split_documents(to_process)
    print(f"   {len(chunks)} chunks generados.")

    openai_client = OpenAI()
    sb = get_supabase()

    total = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        embeddings = embed_texts(openai_client, [c.page_content for c in batch])
        rows = [
            {"content": c.page_content, "embedding": emb, "metadata": c.metadata}
            for c, emb in zip(batch, embeddings)
        ]
        sb.table("documents").insert(rows).execute()
        total += len(rows)
        print(f"   ✅ {total}/{len(chunks)} chunks guardados...")

    print(f"\n🎉 Ingestión completa: {total} chunks nuevos en Supabase.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestar documentos a Supabase")
    parser.add_argument("--docs-dir", default="documents")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--force", action="store_true",
                        help="Reingestar todo aunque ya exista")
    args = parser.parse_args()
    ingest(docs_dir=args.docs_dir, batch_size=args.batch_size, force=args.force)
