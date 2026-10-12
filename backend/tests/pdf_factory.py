"""Genera PDFs mínimos y válidos en memoria para los tests (sin ficheros ni datos reales)."""


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]], padding_bytes: int = 0) -> bytes:
    """Cada página es una lista de líneas. Una página con lista vacía no tiene capa de texto.

    `padding_bytes` añade un comentario PDF de ese tamaño para generar archivos grandes pero válidos.
    """
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    content_ids = [5 + 2 * i for i in range(n)]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for i, lines in enumerate(pages):
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
        ops += [f"({_escape(line)}) Tj T*" for line in lines]
        ops.append("ET")
        stream = "\n".join(ops).encode("cp1252")
        objects[content_ids[i]] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objects[page_ids[i]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ids[i]} 0 R >>"
        ).encode()

    out = bytearray(b"%PDF-1.4\n")
    if padding_bytes:
        out += b"%" + b"x" * padding_bytes + b"\n"
    offsets: dict[int, int] = {}
    for oid in sorted(objects):
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + objects[oid] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for oid in range(1, size):
        out += f"{offsets[oid]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


SAMPLE_CV_LINES = [
    "Ana Garcia Lopez",
    "Desarrolladora Backend - Madrid - ana.garcia@example.com",
    "EXPERIENCIA",
    "Acme Software SL - Desarrolladora Python (2021 - Actualidad)",
    "- Desarrollo de APIs REST con FastAPI y PostgreSQL.",
    "- Despliegue de servicios con Docker y GitHub Actions.",
    "- Reduccion del tiempo de respuesta de la API en un 30%.",
    "Beta Consulting - Programadora junior (2019 - 2021)",
    "- Mantenimiento de aplicaciones Django.",
    "FORMACION",
    "Grado en Ingenieria Informatica - Universidad Complutense de Madrid (2015 - 2019)",
    "HABILIDADES",
    "Python, FastAPI, Django, PostgreSQL, Docker, Git, ingles B2",
]

SAMPLE_CV_PDF = make_pdf([SAMPLE_CV_LINES])

SAMPLE_JOB_OFFER = (
    "Buscamos Backend Developer con experiencia en Python y FastAPI para nuestro equipo de "
    "plataforma. Requisitos: 3 anos de experiencia con Python, APIs REST, PostgreSQL, Docker y "
    "Kubernetes. Valorable experiencia con Terraform y AWS. Ingles C1. Ofrecemos teletrabajo "
    "flexible, formacion continua y un equipo con mucha autonomia tecnica."
)
