# Formal-verification layer on top of the CI image (step P3b).
#   docker build -t aura-hft-formal -f formal/Dockerfile formal
# Ubuntu 24.04 ships yosys + yosys-smtbmc (not the sby front-end), plus z3/boolector.
FROM aura-hft-ci
RUN apt-get update && apt-get install -y --no-install-recommends yosys z3 boolector \
    && rm -rf /var/lib/apt/lists/*
