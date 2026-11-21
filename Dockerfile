# Policy mapping in a container: the same run on Linux, macOS and Windows (Docker Desktop).
#
#   docker build -t coback-policy-mapping .
#   docker run --rm -p 127.0.0.1:8000:8000 \
#     -v "$PWD/../COBACK_Marenthal_Inputs:/app/COBACK_Marenthal_Inputs:ro" \
#     -v "$PWD/companies:/app/coback_policy_mapping/companies" \
#     coback-policy-mapping
#
# The input data is never part of the image: it is mounted read-only at runtime. Reports, reviewer decisions and the
# parse cache are written to the mounted companies/ folder, so they stay on the host exactly as with ./start.sh.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HOME=/tmp
WORKDIR /app/coback_policy_mapping

# packages first, so a code change does not reinstall them: CPU-only PyTorch (no GPU libraries), then the rest
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# the embedding model named in config/app.json, downloaded at build time so the container runs without internet;
# readable and writable for any user id (docker run --user ...)
COPY config/app.json config/app.json
RUN python -c "import json; from sentence_transformers import SentenceTransformer; \
SentenceTransformer(json.load(open('config/app.json'))['semantic']['model'])" \
 && chmod -R a+rwX /opt/hf
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .

EXPOSE 8000
# check the mounted inputs first (names what is missing), then serve on all interfaces inside the container;
# publish the port as 127.0.0.1:8000:8000 so it is reachable only from this machine
CMD ["sh", "-c", "python app.py --check && echo 'Open http://127.0.0.1:8000/ in your browser (or the host port you published).' && exec python app.py --host 0.0.0.0 --port 8000"]
