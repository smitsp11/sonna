"""
Database utility functions for managing Sonna database.

Run from command line:
    python -m backend.db_utils create_tables
    python -m backend.db_utils drop_tables
    python -m backend.db_utils seed_data
"""

import sys
from datetime import datetime, timedelta
from .database import SessionLocal, init_db, drop_db, Base, engine
from .models import User, Conversation, Message, Memory, Reminder, MemoryType, TaskStatus


def create_tables():
    """Create all database tables."""
    print("📦 Creating database tables...")
    init_db()
    print("✅ Tables created successfully!")


def drop_tables():
    """Drop all database tables. WARNING: Deletes all data!"""
    response = input("⚠️  This will DELETE ALL DATA. Are you sure? (yes/no): ")
    if response.lower() == "yes":
        print("🗑️  Dropping all tables...")
        drop_db()
        print("✅ Tables dropped!")
    else:
        print("❌ Operation cancelled.")


def seed_data():
    """Seed database with sample data for testing."""
    print("🌱 Seeding database with sample data...")
    db = SessionLocal()
    
    try:
        # Create sample user
        user = User(
            name="Smit",
            email="smit@example.com",
            preferences={
                "timezone": "America/Toronto",
                "voice_preference": "female",
                "language": "en"
            }
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Created user: {user.name} (ID: {user.id})")
        
        # Create sample conversation
        conversation = Conversation(
            user_id=user.id,
            title="First Chat with Sonna",
            extra_data={"source": "voice"}
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        print(f"✅ Created conversation: {conversation.title} (ID: {conversation.id})")
        
        # Create sample messages
        messages_data = [
            {"role": "user", "content": "Hello Sonna!"},
            {"role": "assistant", "content": "Hi Smit! How can I help you today?"},
            {"role": "user", "content": "What's the weather like?"},
            {"role": "assistant", "content": "I'll need to check that for you. One moment!"}
        ]
        
        for msg_data in messages_data:
            message = Message(
                conversation_id=conversation.id,
                role=msg_data["role"],
                content=msg_data["content"]
            )
            db.add(message)
        db.commit()
        print(f"✅ Created {len(messages_data)} messages")
        
        # Create sample memories
        memories_data = [
            {"content": "User prefers coffee over tea", "type": MemoryType.PREFERENCE},
            {"content": "User is allergic to peanuts", "type": MemoryType.FACT},
            {"content": "User likes rock music", "type": MemoryType.PREFERENCE},
            {"content": "User has a meeting every Monday at 9am", "type": MemoryType.EVENT}
        ]
        
        for mem_data in memories_data:
            memory = Memory(
                user_id=user.id,
                content=mem_data["content"],
                memory_type=mem_data["type"].value,
                source="conversation",
                metadata={"confidence": 0.95}
            )
            db.add(memory)
        db.commit()
        print(f"✅ Created {len(memories_data)} memories")
        
        # Create sample reminders
        now = datetime.utcnow()
        reminders_data = [
            {
                "content": "Call mom",
                "scheduled_time": now + timedelta(hours=2),
                "status": TaskStatus.PENDING
            },
            {
                "content": "Buy groceries",
                "scheduled_time": now + timedelta(days=1),
                "status": TaskStatus.PENDING
            },
            {
                "content": "Dentist appointment",
                "scheduled_time": now + timedelta(days=3, hours=14),
                "status": TaskStatus.PENDING
            }
        ]
        
        for rem_data in reminders_data:
            reminder = Reminder(
                user_id=user.id,
                content=rem_data["content"],
                scheduled_time=rem_data["scheduled_time"],
                status=rem_data["status"].value
            )
            db.add(reminder)
        db.commit()
        print(f"✅ Created {len(reminders_data)} reminders")
        
        print("\n🎉 Database seeded successfully!")
        print(f"   User ID: {user.id}")
        print(f"   Conversation ID: {conversation.id}")
        
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()


def show_data():
    """Display all data in the database."""
    print("📊 Current database contents:\n")
    db = SessionLocal()
    
    try:
        # Show users
        users = db.query(User).all()
        print(f"👥 Users ({len(users)}):")
        for user in users:
            print(f"   - {user.name} ({user.email}) - ID: {user.id}")
        
        # Show conversations
        conversations = db.query(Conversation).all()
        print(f"\n💬 Conversations ({len(conversations)}):")
        for conv in conversations:
            print(f"   - {conv.title} - ID: {conv.id}")
        
        # Show messages
        messages = db.query(Message).all()
        print(f"\n📨 Messages ({len(messages)}):")
        for msg in messages[:5]:  # Show first 5
            print(f"   - [{msg.role}] {msg.content[:50]}...")
        
        # Show memories
        memories = db.query(Memory).all()
        print(f"\n🧠 Memories ({len(memories)}):")
        for mem in memories:
            print(f"   - [{mem.memory_type}] {mem.content}")
        
        # Show reminders
        reminders = db.query(Reminder).all()
        print(f"\n⏰ Reminders ({len(reminders)}):")
        for rem in reminders:
            print(f"   - {rem.content} at {rem.scheduled_time} [{rem.status}]")
            
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.db_utils <command>")
        print("\nCommands:")
        print("  create_tables  - Create all database tables")
        print("  drop_tables    - Drop all tables (WARNING: deletes data)")
        print("  seed_data      - Add sample data for testing")
        print("  show_data      - Display current database contents")
        sys.exit(1)
    
    command = sys.argv[1]
    
    commands = {
        "create_tables": create_tables,
        "drop_tables": drop_tables,
        "seed_data": seed_data,
        "show_data": show_data
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands:", ", ".join(commands.keys()))