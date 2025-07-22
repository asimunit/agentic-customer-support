import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from streamlit_option_menu import option_menu

# Configure page
st.set_page_config(
    page_title="Customer Support Resolver",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE_URL = "http://localhost:8000"

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
        color: #1f77b4;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 0.75rem;
        border-radius: 0.25rem;
        border: 1px solid #c3e6cb;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.75rem;
        border-radius: 0.25rem;
        border: 1px solid #f5c6cb;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .bot-message {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
</style>
""", unsafe_allow_html=True)


# Helper functions
def call_api(endpoint, method="GET", data=None):
    """Make API calls to the backend"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.ConnectionError:
        st.error(
            "⚠️ Cannot connect to backend API. Please ensure the FastAPI server is running on http://localhost:8000")
        return None
    except Exception as e:
        st.error(f"Error calling API: {str(e)}")
        return None


def check_api_health():
    """Check if the API is healthy"""
    health_data = call_api("/health")
    if health_data and health_data.get("success"):
        return health_data["data"]
    return None


# Initialize session state
if "tickets" not in st.session_state:
    st.session_state.tickets = []
if "current_ticket_id" not in st.session_state:
    st.session_state.current_ticket_id = None


# Main App
def main():
    st.markdown(
        '<h1 class="main-header">🎧 Adaptive Customer Support Resolver</h1>',
        unsafe_allow_html=True)

    # Check API health
    health_status = check_api_health()
    if not health_status:
        st.error(
            "⚠️ Backend API is not available. Please start the FastAPI server.")
        st.stop()

    # Display health status in sidebar
    with st.sidebar:
        st.header("🔧 System Status")
        for service, status in health_status.items():
            if status == "healthy" or status == "ready" or status == "connected":
                st.success(f"✅ {service.title()}: {status}")
            else:
                st.warning(f"⚠️ {service.title()}: {status}")

    # Navigation menu
    selected = option_menu(
        menu_title=None,
        options=["Submit Ticket", "Track Ticket", "Analytics Dashboard",
                 "Knowledge Base", "Admin Panel"],
        icons=["ticket-perforated", "search", "graph-up", "book", "gear"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
    )

    if selected == "Submit Ticket":
        submit_ticket_page()
    elif selected == "Track Ticket":
        track_ticket_page()
    elif selected == "Analytics Dashboard":
        analytics_dashboard_page()
    elif selected == "Knowledge Base":
        knowledge_base_page()
    elif selected == "Admin Panel":
        admin_panel_page()


def submit_ticket_page():
    """Customer ticket submission page"""
    st.header("📝 Submit a Support Ticket")

    col1, col2 = st.columns([2, 1])

    with col1:
        with st.form("ticket_form"):
            st.subheader("Tell us about your issue")

            # Customer information
            customer_name = st.text_input("Your Name (Optional)",
                                          placeholder="John Doe")
            customer_email = st.text_input("Email Address (Optional)",
                                           placeholder="john@example.com")

            # Ticket details
            subject = st.text_input("Subject*",
                                    placeholder="Brief description of your issue")
            message = st.text_area(
                "Describe your issue*",
                placeholder="Please provide as much detail as possible...",
                height=150
            )

            # Submit button
            submitted = st.form_submit_button("Submit Ticket", type="primary")

            if submitted:
                if not subject or not message:
                    st.error("Please fill in both subject and message fields.")
                else:
                    # Create ticket
                    ticket_data = {
                        "subject": subject,
                        "message": message,
                        "customer_name": customer_name if customer_name else None,
                        "customer_email": customer_email if customer_email else None,
                        "customer_id": customer_email if customer_email else "anonymous"
                    }

                    # Submit to API
                    with st.spinner("Creating your ticket..."):
                        result = call_api("/tickets", "POST", ticket_data)

                    if result and result.get("success"):
                        ticket_id = result["data"]["ticket_id"]
                        st.session_state.current_ticket_id = ticket_id

                        st.success(
                            f"✅ Ticket created successfully! ID: {ticket_id}")

                        # Automatically process the ticket
                        with st.spinner("Processing your ticket with AI..."):
                            process_result = call_api(
                                f"/tickets/{ticket_id}/process", "POST")

                        if process_result and process_result.get("success"):
                            display_ticket_resolution(process_result["data"])
                        else:
                            st.error(
                                "Failed to process ticket automatically. Please try again.")

    with col2:
        st.subheader("💡 Tips for Better Support")
        st.info("""
        **For faster resolution:**

        🎯 Be specific about the problem

        📋 Include error messages if any

        🔍 Mention what you were trying to do

        📱 Include device/browser info if relevant

        ⏰ Mention when the issue started
        """)

        st.subheader("📊 Average Response Times")
        st.metric("AI Resolution", "< 30 seconds", "⚡")
        st.metric("Human Escalation", "15-30 minutes", "👨‍💼")
        st.metric("Complex Issues", "1-2 hours", "🔧")


def display_ticket_resolution(workflow_result):
    """Display the ticket resolution"""
    st.subheader("🎯 Ticket Resolution")

    # Classification results
    if "classification" in workflow_result:
        classification = workflow_result["classification"]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Category", classification["category"].title())
        with col2:
            st.metric("Priority", classification["priority"].title())
        with col3:
            st.metric("Confidence", f"{classification['confidence']:.0%}")

    # Resolution
    if "resolution" in workflow_result:
        resolution = workflow_result["resolution"]

        st.subheader("📋 Our Response")

        if workflow_result.get("workflow_status") == "escalated":
            st.warning("🔄 Your ticket has been escalated to a human specialist.")

        st.markdown(
            f'<div class="bot-message">{resolution["response"]}</div>',
            unsafe_allow_html=True
        )

        # Confidence indicator
        confidence = resolution.get("confidence", 0)
        if confidence > 0.8:
            st.success(f"✅ High confidence resolution ({confidence:.0%})")
        elif confidence > 0.5:
            st.info(f"ℹ️ Medium confidence resolution ({confidence:.0%})")
        else:
            st.warning(f"⚠️ This issue may need human review ({confidence:.0%})")

        # Knowledge articles used
        if resolution.get("knowledge_articles_used"):
            with st.expander("📚 Reference Articles Used"):
                for article_id in resolution["knowledge_articles_used"]:
                    st.write(f"• Article ID: {article_id}")

    # Prompt for feedback, to be rendered outside this function
    if "current_ticket_id" not in st.session_state:
        st.info("Ticket ID not available for feedback.")



def feedback_form(ticket_id):
    """Feedback form for ticket resolution"""
    if not ticket_id:
        return

    feedback_key = f"feedback_submitted_{ticket_id}"

    if feedback_key not in st.session_state:
        st.session_state[feedback_key] = False

    if st.session_state[feedback_key]:
        st.success("✅ Feedback already submitted for this ticket")
        return

    st.subheader("📝 How was this response?")

    form_key = f"feedback_{ticket_id}_{hash(ticket_id) % 10000}"

    with st.form(key=form_key, clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            was_helpful = st.radio(
                "Was this response helpful?", ["Yes", "No"],
                horizontal=True, key=f"helpful_{form_key}"
            )

        with col2:
            rating = st.select_slider(
                "Rate your experience", options=[1, 2, 3, 4, 5], value=3,
                key=f"rating_{form_key}"
            )

        feedback_text = st.text_area("Additional feedback (optional)", key=f"text_{form_key}")

        submitted = st.form_submit_button("Submit Feedback")

        if submitted:
            feedback_data = {
                "was_helpful": was_helpful == "Yes",
                "customer_rating": rating,
                "feedback_text": feedback_text if feedback_text else None
            }

            with st.spinner("Submitting feedback..."):
                result = call_api(f"/tickets/{ticket_id}/feedback", "POST", feedback_data)

            if result and result.get("success"):
                st.session_state[feedback_key] = True
                st.success("Thank you for your feedback! 🙏")
                if "learning_insights" in result["data"]:
                    st.info("Your feedback helps us improve our AI responses.")
                st.experimental_rerun()
            else:
                st.error("Failed to submit feedback. Please try again.")



def track_ticket_page():
    """Ticket tracking page"""
    st.header("🔍 Track Your Ticket")

    col1, col2 = st.columns([1, 2])

    with col1:
        ticket_id = st.text_input("Enter Ticket ID",
                                  placeholder="e.g., 123e4567-e89b-12d3...")

        if st.button("Track Ticket") and ticket_id:
            result = call_api(f"/tickets/{ticket_id}")

            if result and result.get("success"):
                ticket_data = result["data"]
                display_ticket_details(ticket_data)
            else:
                st.error("Ticket not found. Please check your ticket ID.")

    with col2:
        st.info("""
        **Track your ticket status:**

        🆕 **New** - Just submitted

        ⚡ **Processing** - AI is working on it

        ✅ **Resolved** - AI provided solution

        🔄 **Escalated** - Transferred to human agent

        📞 **In Progress** - Human agent working on it
        """)


def display_ticket_details(ticket_data):
    """Display detailed ticket information"""
    ticket = ticket_data["ticket"]
    resolution = ticket_data.get("resolution")

    st.subheader(f"Ticket: {ticket['subject']}")

    # Ticket info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", (ticket.get("status") or "New").title())
    with col2:
        st.metric("Priority", (ticket.get("priority") or "Medium").title())
    with col3:
        created = datetime.fromisoformat(
            ticket["created_at"].replace("Z", "+00:00"))
        st.metric("Created", created.strftime("%Y-%m-%d %H:%M"))

    # Original message
    with st.expander("📄 Original Message", expanded=True):
        st.write(ticket["message"])

    # Resolution
    if resolution:
        st.subheader("💬 Resolution")
        st.markdown(f'<div class="bot-message">{resolution["response"]}</div>',
                    unsafe_allow_html=True)

        if resolution.get("agent_type") == "escalation":
            st.info("🔄 This ticket has been escalated to our specialist team.")


def analytics_dashboard_page():
    """Analytics dashboard page"""
    st.header("📊 Analytics Dashboard")

    # Get dashboard data
    dashboard_data = call_api("/analytics/dashboard")

    if not dashboard_data or not dashboard_data.get("success"):
        st.error("Failed to load dashboard data")
        return

    data = dashboard_data["data"]
    overview = data["overview"]
    distributions = data["distributions"]

    # Overview metrics
    st.subheader("📈 Overview")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Tickets", overview["total_tickets"])
    with col2:
        st.metric("Resolution Rate", f"{overview['resolution_rate']:.1f}%")
    with col3:
        st.metric("Satisfaction Rate", f"{overview['satisfaction_rate']:.1f}%")
    with col4:
        st.metric("Escalation Rate", f"{overview['escalation_rate']:.1f}%")
    with col5:
        st.metric("Avg Response", "< 30 sec")

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏷️ Tickets by Category")
        if distributions["categories"]:
            fig_categories = px.pie(
                values=list(distributions["categories"].values()),
                names=list(distributions["categories"].keys()),
                title="Category Distribution"
            )
            st.plotly_chart(fig_categories, use_container_width=True)
        else:
            st.info("No category data available")

    with col2:
        st.subheader("⚡ Tickets by Priority")
        if distributions["priorities"]:
            fig_priorities = px.bar(
                x=list(distributions["priorities"].keys()),
                y=list(distributions["priorities"].values()),
                title="Priority Distribution",
                color=list(distributions["priorities"].values()),
                color_continuous_scale="viridis"
            )
            st.plotly_chart(fig_priorities, use_container_width=True)
        else:
            st.info("No priority data available")

    # Recent activity
    st.subheader("🕐 Recent Activity")
    recent = data["recent_activity"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Last 24h Tickets", recent["last_24h_tickets"])
    with col2:
        st.metric("Avg Resolution Time", recent["avg_resolution_time"])
    with col3:
        st.metric("Top Categories", len(recent["top_categories"]))


def knowledge_base_page():
    """Knowledge base search page"""
    st.header("📚 Knowledge Base Search")

    col1, col2 = st.columns([2, 1])

    with col1:
        query = st.text_input("Search knowledge base...",
                              placeholder="e.g., password reset, billing issue")
        category_filter = st.selectbox("Filter by category (optional)",
                                       ["All", "technical", "billing",
                                        "general", "product", "account"])

        if st.button("Search") and query:
            # Prepare search parameters
            search_params = {"query": query, "limit": 10}
            if category_filter != "All":
                search_params["category"] = category_filter

            # Make search request
            endpoint = f"/knowledge/search?query={query}&limit=10"
            if category_filter != "All":
                endpoint += f"&category={category_filter}"

            result = call_api(endpoint)

            if result and result.get("success"):
                search_results = result["data"]["results"]

                if search_results:
                    st.subheader(f"🔍 Found {len(search_results)} articles")

                    for article in search_results:
                        with st.expander(
                                f"📄 {article['title']} (Score: {article['score']:.2f})"):
                            st.write(f"**Category:** {article['category']}")
                            st.write(f"**Relevance:** {article['relevance']}")
                            st.write("**Content:**")
                            st.write(article['content'])
                else:
                    st.info("No articles found matching your search.")
            else:
                st.error("Search failed. Please try again.")

    with col2:
        st.subheader("💡 Search Tips")
        st.info("""
        **For better results:**

        🔤 Use specific keywords

        🏷️ Try different categories

        ❓ Include error messages

        📝 Be descriptive but concise
        """)

        st.subheader("📋 Popular Categories")
        categories = ["Technical Issues", "Billing Questions",
                      "Account Problems", "Product Features", "General Help"]
        for cat in categories:
            if st.button(cat, key=f"cat_{cat}"):
                st.experimental_rerun()


def admin_panel_page():
    """Admin panel for managing the system"""
    st.header("⚚ Admin Panel")

    st.warning(
        "🔐 This is a demo admin panel. In production, this would require authentication.")

    tab1, tab2, tab3 = st.tabs(
        ["📋 All Tickets", "📊 System Metrics", "🔧 System Tools"])

    with tab1:
        st.subheader("All Support Tickets")

        # Get all tickets
        tickets_result = call_api("/tickets?limit=50")

        if tickets_result and tickets_result.get("success"):
            tickets_data = tickets_result["data"]["tickets"]

            if tickets_data:
                # Convert to DataFrame for better display
                df = pd.DataFrame(tickets_data)

                # Format datetime columns
                if "created_at" in df.columns:
                    df["created_at"] = pd.to_datetime(
                        df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")

                # Display table
                st.dataframe(
                    df[["id", "subject", "status", "priority", "created_at",
                        "has_resolution"]],
                    use_container_width=True
                )

                # Bulk operations
                st.subheader("🔄 Bulk Operations")
                if st.button("Refresh Data"):
                    st.experimental_rerun()
            else:
                st.info("No tickets found.")
        else:
            st.error("Failed to load tickets.")

    with tab2:
        st.subheader("System Performance Metrics")

        # Mock system metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("API Response Time", "45ms", "-5ms")
            st.metric("AI Processing Time", "2.3s", "+0.1s")

        with col2:
            st.metric("Elasticsearch Health", "Green", "0")
            st.metric("LLM Availability", "99.9%", "+0.1%")

        with col3:
            st.metric("Memory Usage", "78%", "+2%")
            st.metric("Active Connections", "23", "+5")

        # System health chart
        st.subheader("📈 System Health Over Time")

        # Generate sample data for demo
        dates = pd.date_range(start="2024-01-01", periods=30, freq="D")
        health_data = pd.DataFrame({
            "date": dates,
            "response_time": [40 + i * 0.5 + (i % 7) * 2 for i in range(30)],
            "success_rate": [98 + (i % 3) * 0.5 for i in range(30)]
        })

        fig = px.line(health_data, x="date",
                      y=["response_time", "success_rate"],
                      title="System Performance Metrics")
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("System Tools")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🔄 Data Management")
            if st.button("Clear All Tickets"):
                st.warning("This would clear all tickets in production!")

            if st.button("Export Data"):
                st.info("Export functionality would be implemented here.")

            if st.button("Backup System"):
                st.info("Backup functionality would be implemented here.")

        with col2:
            st.subheader("🤖 AI Model Management")
            if st.button("Retrain Models"):
                st.info("Model retraining would be triggered here.")

            if st.button("Update Knowledge Base"):
                st.info("Knowledge base update would be triggered here.")

            if st.button("System Diagnostics"):
                health_data = check_api_health()
                if health_data:
                    st.json(health_data)


if __name__ == "__main__":
    main()