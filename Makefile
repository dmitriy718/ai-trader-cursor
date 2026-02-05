# Makefile for AI Trading Bot

.PHONY: help setup build up down logs test clean

help:
	@echo "AI Trading Bot - Available commands:"
	@echo "  make setup     - Run setup script"
	@echo "  make build     - Build Docker image"
	@echo "  make up        - Start the bot"
	@echo "  make down      - Stop the bot"
	@echo "  make logs      - View logs"
	@echo "  make test      - Run stress test"
	@echo "  make clean     - Clean up containers and volumes"

setup:
	@bash scripts/setup.sh

build:
	@docker-compose build

up:
	@docker-compose up -d

down:
	@docker-compose down

logs:
	@docker-compose logs -f trading-bot

test:
	@python scripts/stress_test.py --duration 1

clean:
	@docker-compose down -v
	@docker system prune -f
