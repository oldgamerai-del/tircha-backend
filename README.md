# Tircha Backend API
# AI Blog Generation Service

This is the Tircha Backend API - an AI-powered blog generation service.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run: `uvicorn main:app --reload`

## API Routes

- `POST /api/blog/generate` - Generate a blog post
- `POST /api/keywords/research` - Research keywords
- `POST /admin/create-key` - Create API key (admin)
- `POST /webhooks/razorpay` - Razorpay webhook
