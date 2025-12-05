# Roadmap

## v0.1.0 (Current)
- [x] Core template engine
- [x] All field types
- [x] Rate control
- [x] Output sinks
- [x] Corruption engine
- [x] LLM integration
- [x] Presets
- [x] Parallel streams
- [x] Burst patterns

## v0.1.1
- [x] Additional presets (19 total)
  - Web servers: apache, nginx-error, haproxy
  - Databases: postgres, mysql, mongodb
  - Infrastructure: kubernetes, docker, terraform
  - Security: auth, sshd, firewall, audit
  - Applications: java, python, nodejs

## v0.2.0 (Current)
- [x] Per-stream rate syntax (`--stream nginx:rate=10`)
- [x] Jinja2 templating for complex patterns
- [x] Conditional field generation (`when:` clause)
- [x] Plugin system for custom field types
- [x] Configuration profiles (`--profile`)
- [x] Docker image with multi-stage build
- [x] Example templates and profiles
- [x] CLI integration tests (106 total tests)

## v0.3.0 (Future)
- [ ] TUI dashboard with live stats
- [ ] Replay mode (from existing logs)
- [ ] Log file watching and augmentation
- [ ] HTTP output sink with batching

## v1.0.0 (Future)
- [ ] Distributed workers
- [ ] Kubernetes operator
- [ ] Prometheus metrics endpoint
- [ ] Schema inference from sample logs
