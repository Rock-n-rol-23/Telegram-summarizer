# Operational Runbook

## System Overview

This runbook covers operational procedures for the Telegram Summarization Bot v2.0 in production environments.

## Health Monitoring

### Health Check Endpoints

```bash
# Comprehensive health check
curl https://your-domain.com/health

# Quick readiness check
curl https://your-domain.com/ready

# Liveness probe
curl https://your-domain.com/live
```

### Key Metrics to Monitor

- **Response Times**: Health endpoint should respond < 2s
- **Error Rates**: Keep < 5% for user requests
- **Memory Usage**: Monitor for memory leaks
- **Database Connections**: Watch connection pool utilization
- **External API Calls**: Monitor Groq API latency and errors

## Configuration Management

### Environment Variables

#### Critical Settings
```bash
# Core functionality
TELEGRAM_BOT_TOKEN=your_token_here
GROQ_API_KEY=your_groq_key
DATABASE_URL=postgresql://...

# Security
WEBHOOK_SECRET_TOKEN=random_secret
MIME_TYPE_VALIDATION=1

# Performance
MAX_REQUESTS_PER_MINUTE=20
GLOBAL_QPS_LIMIT=10
```

#### Feature Toggles
```bash
# Disable heavy features during high load
ENABLE_OCR=0
ENABLE_YOUTUBE=0
ENABLE_PDF_PROCESSING=0

# Enable for normal operation
ENABLE_OCR=1
ENABLE_YOUTUBE=1
ENABLE_PDF_PROCESSING=1
```

### Rate Limit Adjustments

**Increase limits during normal operation:**
```bash
MAX_REQUESTS_PER_MINUTE=50
GLOBAL_QPS_LIMIT=20
```

**Decrease during incidents:**
```bash
MAX_REQUESTS_PER_MINUTE=5
GLOBAL_QPS_LIMIT=2
```

## Key Rotation

### Rotating Telegram Bot Token

1. **Create new bot token via @BotFather**
2. **Test new token in staging**
3. **Update production environment**
   ```bash
   # Cloud Run
   gcloud run services update telegram-bot \
     --set-env-vars="TELEGRAM_BOT_TOKEN=new_token"
   
   # Docker
   docker run --env-file .env.new telegram-bot
   ```
4. **Verify bot responds**
5. **Revoke old token in @BotFather**

### Rotating Groq API Key

1. **Generate new key in Groq Console**
2. **Test in staging environment**
3. **Update production**
   ```bash
   gcloud run services update telegram-bot \
     --set-env-vars="GROQ_API_KEY=new_key"
   ```
4. **Monitor summarization success rate**
5. **Revoke old key**

### Rotating Database Credentials

1. **Create new database user with same permissions**
2. **Update connection string**
   ```bash
   DATABASE_URL=postgresql://newuser:newpass@host:port/dbname
   ```
3. **Test database connectivity**
4. **Apply configuration**
5. **Remove old database user**

## Performance Tuning

### High Load Scenarios

**Temporarily disable heavy features:**
```bash
ENABLE_OCR=0
ENABLE_YOUTUBE=0
BACKGROUND_TASK_TIMEOUT=60  # Reduce from 300s
```

**Increase concurrency:**
```bash
WORKERS=4  # Increase gunicorn workers
USE_GUNICORN=1
```

**Database optimization:**
```bash
# PostgreSQL tuning
SQLALCHEMY_ENGINE_OPTIONS='{"pool_size": 20, "max_overflow": 30}'
```

### Memory Management

**Monitor temp file usage:**
```bash
# Check disk usage
curl https://your-domain.com/health | jq '.disk_usage'

# Force cleanup if needed
TEMP_FILE_RETENTION_HOURS=1
AUTO_CLEANUP_INTERVAL=600  # 10 minutes
```

## Incident Response

### Bot Not Responding

1. **Check health endpoint**
   ```bash
   curl -f https://your-domain.com/health || echo "Health check failed"
   ```

2. **Verify Telegram connectivity**
   ```bash
   curl -f "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
   ```

3. **Check logs for errors**
   ```bash
   # Cloud Run
   gcloud logs read --service=telegram-bot --limit=50
   
   # Docker
   docker logs telegram-bot --tail=50
   ```

4. **Common fixes**
   - Restart service
   - Check environment variables
   - Verify network connectivity
   - Scale up resources

### High Error Rates

1. **Check external service status**
   ```bash
   # Test Groq API
   curl -H "Authorization: Bearer $GROQ_API_KEY" \
        https://api.groq.com/openai/v1/models
   ```

2. **Enable circuit breakers**
   - Errors will automatically trigger circuit breakers
   - Check logs for circuit breaker state changes

3. **Reduce load temporarily**
   ```bash
   MAX_REQUESTS_PER_MINUTE=5
   GLOBAL_QPS_LIMIT=1
   ```

### Database Issues

1. **Check database connectivity**
   ```bash
   # Test connection
   psql $DATABASE_URL -c "SELECT version();"
   ```

2. **Monitor connection pool**
   ```bash
   curl https://your-domain.com/health | jq '.database.pool_status'
   ```

3. **Emergency fallback to SQLite**
   ```bash
   DATABASE_URL=sqlite:///emergency.db
   ```

### Memory/Resource Issues

1. **Check resource usage**
   ```bash
   # Cloud Run
   gcloud monitoring metrics list --filter="resource.type=cloud_run_revision"
   ```

2. **Enable aggressive cleanup**
   ```bash
   TEMP_FILE_RETENTION_HOURS=0.5
   AUTO_CLEANUP_INTERVAL=300
   ```

3. **Disable heavy features**
   ```bash
   ENABLE_OCR=0
   ENABLE_YOUTUBE=0
   ENABLE_PDF_PROCESSING=0
   ```

## Database Maintenance

### Regular Maintenance

**Weekly cleanup:**
```sql
-- Remove old user requests (>30 days)
DELETE FROM user_requests 
WHERE created_at < NOW() - INTERVAL '30 days';

-- Clean web cache (>3 days)
DELETE FROM web_cache 
WHERE cached_at < NOW() - INTERVAL '3 days';

-- Update statistics
ANALYZE;
```

**Monthly optimization:**
```sql
-- Reindex for performance
REINDEX DATABASE your_database_name;

-- Vacuum for space reclamation
VACUUM ANALYZE;
```

### Backup Procedures

**Automated backup:**
```bash
# PostgreSQL backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Compress and store
gzip backup_*.sql
gsutil cp backup_*.sql.gz gs://your-backup-bucket/
```

**Restore procedure:**
```bash
# Restore from backup
gunzip backup_20250822_080000.sql.gz
psql $DATABASE_URL < backup_20250822_080000.sql
```

### Migration Management

**Apply migrations:**
```bash
# Check current version
alembic current

# Apply pending migrations
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

**Create new migration:**
```bash
# After modifying database schema
alembic revision --autogenerate -m "Add new feature table"
alembic upgrade head
```

## Security Procedures

### Security Incident Response

1. **Suspected API key compromise**
   - Immediately rotate affected keys
   - Check logs for unauthorized usage
   - Monitor for unusual activity patterns

2. **SSRF attack detected**
   - Check logs for blocked internal requests
   - Verify SSRF protection is enabled
   - Review recent URL processing requests

3. **Rate limit bypass**
   - Check rate limiting configuration
   - Look for distributed attack patterns
   - Consider temporary IP blocking

### Security Hardening

**Regular security checks:**
```bash
# Verify SSRF protection
curl -f https://your-domain.com/health | jq '.security.ssrf_protection'

# Check file validation
curl -f https://your-domain.com/health | jq '.security.mime_validation'

# Review webhook security
curl -f https://your-domain.com/health | jq '.security.webhook_verification'
```

## Scaling Guidelines

### Horizontal Scaling

**Cloud Run scaling:**
```bash
gcloud run services update telegram-bot \
  --min-instances=2 \
  --max-instances=10 \
  --concurrency=100
```

**Load balancer setup:**
- Multiple regions for global users
- Health check configuration
- Auto-scaling based on CPU/memory

### Vertical Scaling

**Resource allocation:**
```bash
# Increase memory and CPU
gcloud run services update telegram-bot \
  --memory=2Gi \
  --cpu=2
```

**Database scaling:**
- Connection pool tuning
- Read replicas for analytics
- Vertical scaling of database instance

## Monitoring Alerts

### Critical Alerts

1. **Health check failing**
   - Alert if health endpoint returns non-200 for >2 minutes
   - Auto-restart service after 3 failures

2. **High error rate**
   - Alert if error rate >10% for >5 minutes
   - Trigger rate limiting if >25% errors

3. **External API failures**
   - Alert if Groq API error rate >20%
   - Enable circuit breaker if >50% failures

### Warning Alerts

1. **High resource usage**
   - Memory usage >80%
   - CPU usage >70%
   - Disk usage >90%

2. **Performance degradation**
   - Response time >5s average
   - Database connection pool >80% utilized
   - Rate limit near maximum

## Troubleshooting Checklist

### Before Contacting Support

- [ ] Check health endpoints
- [ ] Verify environment variables
- [ ] Review recent logs
- [ ] Test external API connectivity
- [ ] Check resource utilization
- [ ] Verify database connectivity
- [ ] Test with simple request

### Information to Gather

- Service version and deployment time
- Error messages and stack traces
- User reports and reproduction steps
- System metrics and resource usage
- Recent configuration changes
- External service status

---

**Last Updated**: 2025-08-22  
**Next Review**: 2025-09-22