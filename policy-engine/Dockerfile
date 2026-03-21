FROM openpolicyagent/opa:latest

# Copy OPA server configuration
COPY opa-config.yaml /etc/opa/config.yaml

# Copy Rego policies
COPY policies/ /policies/

# Copy default data (configurable values referenced by policies)
COPY data/ /data/

# Expose OPA HTTP API port (internal Docker network only)
EXPOSE 8181

# Expose diagnostic port for health checks
EXPOSE 8282

# Run OPA server with policies and data loaded
ENTRYPOINT ["opa"]
CMD [ \
  "run", \
  "--server", \
  "--config-file=/etc/opa/config.yaml", \
  "--addr=:8181", \
  "--diagnostic-addr=:8282", \
  "/policies", \
  "/data" \
]
