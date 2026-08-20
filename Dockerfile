FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "src.orchestration.run_pipeline"]

# TODO: hardening for a production/submission-ready image (not required for
# local dev, but worth doing before the 27four demo/submission):
#   1. Run as a non-root user: add
#        RUN useradd --create-home appuser
#        USER appuser
#      after the pip install step (pip install needs root for system
#      packages in some base images — test that this doesn't break the
#      build with python:3.11-slim specifically).
#   2. Add a .dockerignore (new file, repo root) excluding .git, __pycache__,
#      .pytest_cache, tests/, and .env — none of which need to ship in the
#      image, and .env in particular should never be baked into an image.
#   3. Consider splitting requirements into requirements.txt (runtime) and
#      requirements-dev.txt (pytest, etc.) so the production image doesn't
#      carry test dependencies — decide if that split is worth the added
#      complexity for a student project of this scope.
