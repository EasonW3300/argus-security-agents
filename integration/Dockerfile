FROM ghcr.io/chaitin/agent-compose-guest:latest

COPY scenarios/scenario-01-alert-analysis/eval/requirements.txt /tmp/scenario-01-requirements.txt
COPY scenarios/scenario-02-document-rag/eval/requirements.txt /tmp/scenario-02-requirements.txt
COPY scenarios/scenario-03-security-tool-calling/eval/requirements.txt /tmp/scenario-03-requirements.txt
COPY scenarios/scenario-04-security-briefing/eval/requirements.txt /tmp/scenario-04-requirements.txt

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    -r /tmp/scenario-01-requirements.txt \
    -r /tmp/scenario-02-requirements.txt \
    -r /tmp/scenario-03-requirements.txt \
    -r /tmp/scenario-04-requirements.txt
