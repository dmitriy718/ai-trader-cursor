# Security Best Practices

This document outlines security best practices for the AI Trading Bot project.

## 🔒 Secrets Protection

### Never Commit These Files

The `.gitignore` file is configured to protect the following sensitive information:

1. **Environment Variables** (`.env` files)
   - Binance API keys and secrets
   - Telegram bot tokens
   - Database credentials
   - Any other sensitive configuration

2. **Database Files** (`*.db`, `*.sqlite`)
   - Contains trading history
   - Contains account balances
   - Contains order information

3. **Log Files** (`*.log`)
   - May contain API keys in error messages
   - Contains trading activity
   - Contains system information

4. **Model Files** (`models/*.tflite`, `models/*.h5`)
   - Proprietary ML models
   - Trained model weights

5. **Private Keys** (`*.pem`, `*.key`)
   - SSL certificates
   - SSH keys
   - GPG keys

### Files That ARE Safe to Commit

- `.env.example` - Template file with placeholder values
- `config/config.yaml` - Public configuration (no secrets)
- `README.md` - Documentation
- Source code (`.py` files)
- Test files
- Docker configuration files

## 🛡️ Security Checklist

Before committing code, verify:

- [ ] No `.env` file is tracked
- [ ] No API keys or secrets in code comments
- [ ] No hardcoded credentials in source files
- [ ] No database files committed
- [ ] No log files committed
- [ ] `.env.example` exists with placeholder values
- [ ] All secrets use environment variables

## 🔍 How to Verify Secrets Are Protected

### Check Git Status
```bash
# Should NOT show .env, *.db, *.log files
git status

# Check if any secrets are tracked
git ls-files | grep -E '\.(env|db|log)$'
```

### Search for Hardcoded Secrets
```bash
# Search for potential API keys in code
grep -r "api.*key.*=" src/ --exclude-dir=__pycache__
grep -r "secret.*=" src/ --exclude-dir=__pycache__
grep -r "BINANCE_API" src/ --exclude-dir=__pycache__
```

### Check Git History
```bash
# Check if secrets were ever committed (should return nothing)
git log --all --full-history --source -- "*.env"
git log --all --full-history --source -- "*.db"
```

## 🚨 If Secrets Were Accidentally Committed

If you accidentally committed secrets:

1. **Immediately rotate the compromised credentials**
   - Generate new Binance API keys
   - Revoke old Telegram bot token
   - Change any other exposed secrets

2. **Remove from Git history** (if repository is private):
   ```bash
   # Remove file from history
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   
   # Force push (WARNING: Only if private repo!)
   git push origin --force --all
   ```

3. **If repository is public**:
   - Consider the secrets compromised
   - Rotate ALL credentials immediately
   - Review access logs for unauthorized access

## 📋 Environment Variables Setup

### Required Variables

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Then edit `.env` and add your actual credentials:

```env
# Binance API (REQUIRED)
BINANCE_API_KEY=your_actual_api_key_here
BINANCE_API_SECRET=your_actual_api_secret_here
BINANCE_TESTNET=true  # Start with testnet!

# Trading Configuration
TRADING_ENABLED=false  # Keep disabled until ready

# Telegram Notifications (OPTIONAL)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
NOTIFICATIONS_ENABLED=false
```

### Environment Variable Security

1. **Never share `.env` files**
2. **Use different `.env` files for different environments**
3. **Rotate credentials regularly**
4. **Use least-privilege API keys** (read-only + trade, no withdraw)

## 🔐 API Key Permissions

When creating Binance API keys:

- ✅ **Enable**: Read Info, Enable Trading
- ❌ **Disable**: Enable Withdrawals, Enable Internal Transfer
- ✅ **IP Restriction**: Restrict to your server IP (if possible)
- ✅ **Whitelist**: Only allow specific IPs

## 🧪 Testing Without Secrets

For testing and CI/CD:

1. Use `.env.example` as a template
2. Use testnet API keys (safe to share)
3. Use dummy values for non-critical services
4. Never use production credentials in tests

## 📝 Code Review Checklist

When reviewing code, check:

- [ ] No secrets in code
- [ ] No secrets in comments
- [ ] No secrets in commit messages
- [ ] Environment variables used for all secrets
- [ ] `.env.example` updated if new variables added
- [ ] Documentation updated if security-related

## 🐳 Docker Security

### Docker Secrets

Never put secrets in Dockerfiles or docker-compose.yml:

```yaml
# ❌ BAD - Never do this
environment:
  BINANCE_API_KEY: "hardcoded_key"

# ✅ GOOD - Use env_file
env_file:
  - .env
```

### Docker Volumes

Database and log files are mounted as volumes (not in image):

```yaml
volumes:
  - ./data:/app/data      # Database files
  - ./logs:/app/logs      # Log files
```

## 🔄 Regular Security Maintenance

1. **Rotate credentials quarterly**
2. **Review `.gitignore` regularly**
3. **Audit committed files** for secrets
4. **Update dependencies** for security patches
5. **Monitor access logs** for suspicious activity

## 📚 Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [Binance API Security](https://www.binance.com/en/support/faq/360002502072)

## ⚠️ Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** create a public issue
2. **DO** contact the maintainer privately
3. **DO** provide detailed information
4. **DO** allow time for fix before disclosure

---

**Remember**: Security is everyone's responsibility. When in doubt, ask!
