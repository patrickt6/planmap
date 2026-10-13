# Todo app plan

## Track A: tasks

### 1. Task model and storage (shipped, PR #3)
SQLite table for tasks with title, notes, done flag and timestamps.

### 2. Task list view
Depends on: 1
Show open tasks first, done tasks folded at the bottom.

### 3. Quick add from the keyboard
Depends on: 2
Press "n" anywhere to add a task.

### 4. Due dates
Depends on: 1
Optional due date on each task, sorted by soonest.

### 5. Reminders
Depends on: 4
Send a reminder an hour before a task is due.

## Track B: accounts

### 6. Sign in with email link
Magic link sign-in, no passwords.

### 7. Shared lists
Depends on: 2, 6
Invite someone to a list by email.

### 8. Offline mode
Depends on: 2
Queue edits while offline and sync when back.

## Track C: polish

### 9. Dark theme
Follow the system setting, with a manual toggle.

### 10. Recurring tasks
Depends on: 4
Repeat daily, weekly or monthly.
