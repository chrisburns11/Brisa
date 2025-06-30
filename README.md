
# Brisa - Tee Time Management App

Brisa is a lightweight, mobile-friendly web app designed to manage tee time signups for golf tournaments such as the U.S. Open and U.S. Amateur events. Built with Flask and deployed on Render.

## Features
- Tournament selection page
- Live tee time availability
- Registration with email/SMS confirmation
- Max 4 players per tee time

## Setup
1. Install requirements:
   pip install -r requirements.txt

2. Initialize database and populate tee times:
   flask create_tee_times

3. Run app locally:
   flask run
