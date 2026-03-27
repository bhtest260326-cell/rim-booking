# Rim Repair Booking Automation

Automated booking system for mobile rim repair business.

## What it does

1. Polls Gmail every 60 seconds for new customer emails
2. Uses Claude AI to extract booking details (name, vehicle, date, address, service)
3. If details are incomplete, auto-replies to customer requesting missing info
4. Sends you an SMS with booking details for YES/NO confirmation
5. On YES: creates Google Calendar event + sends customer confirmation SMS + email
6. On NO: sends customer a polite decline message
7. If you reply with corrections (e.g. "change time to 11am"), updates booking and re-confirms
8. Sends customer a reminder SMS the day before their booking
9. Sends customer a Google review request ~3 hours after job completion

## Environment Variables

Set all of these in Railway before deploying:

```
ANTHROPIC_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
OWNER_MOBILE=
OWNER_EMAIL=                  # Optional — fallback email when SMS fails (calendar invite sent here)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=
GMAIL_ADDRESS=              # Your Gmail address (to avoid processing your own sent emails)
GOOGLE_REVIEW_LINK=         # Optional: your Google Maps review link
STATE_FILE=                 # Optional: defaults to /data/booking_state.json
```

## Deploy to Railway

1. Create a new project at railway.app
2. Connect your GitHub repo OR use Railway CLI to push this folder
3. Add all environment variables above in Railway → Variables tab
4. Add a Volume in Railway (mount path: /data) for persistent booking state
5. Deploy

## Owner SMS Commands

When you receive a booking request SMS:
- Reply `YES` → confirms booking, creates calendar event, notifies customer
- Reply `NO` → declines booking, notifies customer
- Reply with any correction → e.g. `change time to 2pm`, `address is 14 Smith St Balcatta` → updates booking and re-sends for confirmation

## Project Structure

```
src/
  main.py          - Main loop
  gmail_poller.py  - Gmail inbox reader
  ai_parser.py     - Claude AI extraction + formatting
  twilio_handler.py - SMS send/receive + owner confirmation flow
  calendar_handler.py - Google Calendar event creation
  scheduler.py     - Day-prior reminders + review requests
  state_manager.py - Booking state persistence
```
