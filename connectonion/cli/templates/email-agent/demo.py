"""Demo script to showcase the Email Agent capabilities."""

from agent import EmailManager

def demo():
    """Run a demo of the email agent capabilities."""
    
    print("🎬 Email Agent Demo")
    print("=" * 50)
    
    # Create email manager
    manager = EmailManager()
    
    # Demo 1: Check inbox
    print("\n📬 Demo 1: Checking Inbox")
    print("-" * 30)
    result = manager.check_inbox(limit=5)
    print(result)
    
    # Demo 2: Search emails
    print("\n🔍 Demo 2: Searching Emails")
    print("-" * 30)
    result = manager.search_emails("meeting")
    print(result)
    
    # Demo 3: Compose and send
    print("\n✉️ Demo 3: Composing Email")
    print("-" * 30)
    result = manager.compose_and_send(
        to="demo@example.com",
        subject="Demo Email from ConnectOnion",
        message="This is a demonstration of the email agent capabilities."
    )
    print(result)
    
    # Demo 4: Statistics
    print("\n📊 Demo 4: Email Statistics")
    print("-" * 30)
    result = manager.get_statistics()
    print(result)
    
    # Demo 5: Auto-respond simulation
    print("\n🤖 Demo 5: Auto-Response")
    print("-" * 30)
    print("Auto-response would handle emails with these keywords:")
    for keyword, response in manager.auto_responses.items():
        print(f"   • '{keyword}': {response[:50]}...")
    
    print("\n" + "=" * 50)
    print("✅ Demo Complete!")
    print("\nThe Email Agent can:")
    print("  ✅ Check and summarize inbox")
    print("  ✅ Send and reply to emails")
    print("  ✅ Search emails by content")
    print("  ✅ Auto-respond to keywords")
    print("  ✅ Mark emails as read")
    print("  ✅ Provide statistics")
    print("\nRun 'python agent.py' for the interactive experience!")

if __name__ == "__main__":
    demo()