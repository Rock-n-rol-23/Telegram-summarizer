# Как получить бесплатный API ключ OpenRouter

OpenRouter предоставляет доступ к множеству LLM моделей через единый API, включая **бесплатные модели**.

## Шаги для получения бесплатного ключа:

1. **Зарегистрируйтесь на OpenRouter**
   - Перейдите на https://openrouter.ai/
   - Нажмите "Sign In" → "Continue with Google" (или другой способ)

2. **Получите API ключ**
   - После входа откройте https://openrouter.ai/keys
   - Нажмите "Create Key"
   - Скопируйте сгенерированный ключ (он начинается с `sk-or-...`)

3. **Добавьте ключ в .env**
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
   ```

4. **Настройте бесплатную модель** (опционально)
   ```bash
   # Используйте бесплатную модель по умолчанию
   OPENROUTER_PRIMARY_MODEL=meta-llama/llama-3.1-8b-instruct:free
   ```

## Доступные бесплатные модели:

- `meta-llama/llama-3.1-8b-instruct:free` - Llama 3.1 8B (рекомендуется)
- `google/gemini-flash-1.5:free` - Gemini 1.5 Flash
- `mistralai/mistral-7b-instruct:free` - Mistral 7B
- `deepseek/deepseek-chat-v3.1:free` - DeepSeek v3.1

Полный список: https://openrouter.ai/models?order=newest&supported_parameters=tools&max_price=0

## Бесплатные лимиты:

- **$1 в месяц** бесплатных кредитов для новых пользователей
- Без необходимости привязки карты
- После исчерпания лимита - можно пополнить или подождать следующего месяца

## Как работает fallback в боте:

1. Бот сначала пробует **Groq** (если есть ключ)
2. Если Groq недоступен или исчерпан лимит → переключается на **OpenRouter**
3. Используется бесплатная модель `meta-llama/llama-3.1-8b-instruct:free`
4. Вы видите в логах: `"Использован OpenRouter (fallback)"`

## Альтернативные бесплатные провайдеры:

Если OpenRouter тоже исчерпан, можно добавить:

- **Together.ai** - https://api.together.xyz/ ($25 бесплатных кредитов)
- **Hugging Face** - https://huggingface.co/inference-api (бесплатный tier)
- **Replicate** - https://replicate.com/ ($10 бесплатных кредитов)

---

**Важно**: Храните API ключи в `.env` файле и никогда не коммитьте их в Git!
