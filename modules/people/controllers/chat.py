from flask import current_app
from flask import jsonify
from flask import render_template
from flask import request
from flask_login import current_user
from flask_login import login_required
from flask_socketio import emit
from flask_socketio import join_room
from flask_socketio import leave_room
from flask import redirect
from flask import url_for

from system.db.database import db
from modules.core.models.user import User

from ..models.chat import Channel
from ..models.chat import Chat
from ..models.chat import InteractionType
from ..models.chat import ChatMessageState
from . import blueprint
from system.utils import is_mobile



@blueprint.route("/chat")
@login_required
def chat():
    """Company chat page"""
    channels = Channel.query.all()
    default_channel = Channel.query.filter_by(name="general").first()
    if not default_channel:
        default_channel = Channel(
            name="general", description="General discussion channel", created_by_id=current_user.id
        )
        db.session.add(default_channel)
        db.session.commit()

    if is_mobile():
        return render_template(
            "chat/index-mobile.html",
            channels=channels,
            ChatMessageState=ChatMessageState,
            title="Chat"
        )
    
    return render_template(
        "chat/index-desktop.html",
        active_page="chat",
        title="Company Chat",
        channels=channels,
        default_channel=default_channel,
        module_home="people_bp.people_home",
        ChatMessageState=ChatMessageState
    )


@blueprint.route("/chat/channels/<channel_name>/messages")
@login_required
def get_channel_messages(channel_name):
    """Get messages for a specific channel"""
    try:
        # Get query parameters
        before_id = request.args.get('before_id', type=int)
        limit = request.args.get('limit', 10, type=int)
        pinned_only = request.args.get('pinned_only', '').lower() == 'true'
        search_query = request.args.get('search', '').strip()
        
        # Get channel
        channel = Channel.query.filter_by(name=channel_name).first()
        if not channel:
            return f"Channel {channel_name} not found", 404
            
        # Build base query
        query = channel.messages
        
        # Apply filters
        if pinned_only:
            query = query.filter(Chat.pinned == True)
            
        if search_query:
            search_terms = f"%{search_query}%"
            query = query.join(User, Chat.author_id == User.id).filter(
                db.or_(
                    Chat.content.ilike(search_terms),
                    (User.first_name + ' ' + User.last_name).ilike(search_terms)
                )
            )
            
        # Get total count
        total_messages = query.count()
        if total_messages == 0:
            return render_template(
                "chat/partials/chat-list-desktop.html",
                chats=[],
                current_user=current_user,
                channel_description=channel.description,
                ChatMessageState=ChatMessageState,
                has_more=False,
                oldest_id=None,
                channel_name=channel_name
            )
        
        # If before_id is not provided, get the latest messages
        if not before_id:
            messages = query.order_by(Chat.created_at.desc()).limit(limit).all()
            messages = messages[::-1]  # Reverse to show in ascending order
            has_more = query.filter(Chat.id < messages[0].id).first() is not None
            oldest_id = messages[0].id
        else:
            # Get messages before the given ID
            messages = query.filter(Chat.id < before_id).order_by(Chat.created_at.desc()).limit(limit).all()
            messages = messages[::-1]  # Reverse to show in ascending order
            has_more = query.filter(Chat.id < messages[0].id).first() is not None if messages else False
            oldest_id = messages[0].id if messages else None
            
        # Mark messages as read for the current user
        for message in messages:
            ChatMessageState.mark_message_read(current_user.id, message.id)
        db.session.commit()
        
        return render_template(
            "chat/partials/chat-list-desktop.html",
            chats=messages,
            current_user=current_user,
            channel_description=channel.description,
            ChatMessageState=ChatMessageState,
            has_more=has_more,
            oldest_id=oldest_id,
            channel_name=channel_name
        )
            
    except Exception as e:
        current_app.logger.error(f"Error getting channel messages: {str(e)}")
        return str(e), 500


@blueprint.route("/chat/channels", methods=["POST"])
@login_required
def create_channel():
    """Create a new channel"""
    try:
        # Check if user is admin
        if not current_user.is_admin:
            return "Unauthorized: Only administrators can create channels", 403

        name = request.form.get("name")
        if not name:
            return "Channel name is required", 400

        name = name.lower().replace(" ", "-")
        description = request.form.get("description")
        is_private = bool(request.form.get("is_private", False))

        # Check if channel already exists
        existing = Channel.query.filter_by(name=name).first()
        if existing:
            return "Channel already exists", 400

        channel = Channel(
            name=name, description=description, created_by_id=current_user.id, is_private=is_private
        )
        db.session.add(channel)
        db.session.commit()

        # Emit WebSocket event for new channel
        current_app.socketio.emit("channel_created", {
            "name": channel.name, 
            "description": channel.description
        })  # No 'to' needed since this should go to everyone

        return jsonify({"id": channel.id, "name": channel.name})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating channel: {str(e)}")
        return str(e), 400


@blueprint.route("/chat/create", methods=["POST"])
@login_required
def create_chat():
    """Create a new chat message"""
    try:
        content = request.form.get("content")
        channel_name = request.form.get("channel", "general")
        pinned = bool(request.form.get("pin", False))

        # Validate required fields
        if not content:
            return "Content is required", 400

        # Get or create channel
        channel = Channel.query.filter_by(name=channel_name).first()
        if not channel:
            return f"Channel {channel_name} not found", 404

        chat = Chat(
            content=content, author_id=current_user.id, channel_id=channel.id, pinned=pinned
        )
        db.session.add(chat)
        db.session.flush()  # Get the chat ID without committing
        
        # Create or update message states for all users except the author
        users = User.query.filter(User.id != current_user.id).all()
        for user in users:
            # Get or create read state for this user/channel
            read_state = ChatMessageState.query.filter_by(
                user_id=user.id,
                channel_id=channel.id,
                interaction_type=InteractionType.READ
            ).first()
            
            if read_state:
                # Update existing state to mark new message as unread
                # Keep the last_read_message_id as is, which means this new message is unread
                read_state.updated_at = db.func.now()
            else:
                # Create new state
                state = ChatMessageState(
                    user_id=user.id,
                    message_id=chat.id,
                    channel_id=channel.id,
                    interaction_type=InteractionType.READ,
                    data={'last_read_message_id': None}  # None indicates unread
                )
                db.session.add(state)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error while creating chat: {str(e)}")
            return "Database error occurred. Please try again.", 500

        # Emit two events:
        # 1. To users in the channel to refresh their messages
        current_app.socketio.emit("chat_changed", {
            "channel": channel_name,
            "message_id": chat.id,
            "author_id": current_user.id,
            "type": "refresh"
        }, to=channel_name)

        # 2. To all users to update unread badges
        current_app.socketio.emit("message_created", {
            "channel": channel_name,
            "message_id": chat.id,
            "author_id": current_user.id
        })  # No 'to' means broadcast to everyone

        return ""
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating chat: {str(e)}")
        return str(e), 400


@blueprint.route("/chat/<int:chat_id>/pin", methods=["POST"])
@login_required
def toggle_pin(chat_id):
    """Toggle pin status of a chat"""
    try:
        chat = Chat.query.get_or_404(chat_id)
        if not current_user.is_admin and not chat.is_author:
            return jsonify({"error": "Unauthorized"}), 403

        is_pinned = chat.toggle_pin()
        current_app.socketio.emit("chat_changed", {
            "channel": chat.channel.name,
            "message_id": chat.id,
            "author_id": current_user.id,
            "pinned": is_pinned
        }, to=chat.channel.name)
        return jsonify({"pinned": is_pinned})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@blueprint.route("/chat/<int:chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    """Delete a chat message"""
    try:
        chat = Chat.query.get_or_404(chat_id)
        if not current_user.is_admin and not chat.is_author:
            return jsonify({"error": "Unauthorized"}), 403

        channel_name = chat.channel.name
        
        # First delete all associated message states
        ChatMessageState.query.filter_by(message_id=chat_id).delete()
        
        # Then delete the message
        db.session.delete(chat)
        db.session.commit()

        current_app.socketio.emit("chat_changed", {"channel": channel_name}, room=channel_name)
        return "", 204
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@blueprint.route("/chat/channels/<channel_name>/mark_read", methods=["POST"])
@login_required
def mark_channel_read(channel_name):
    """Mark all messages in a channel as read for the current user"""
    try:
        channel = Channel.query.filter_by(name=channel_name).first()
        if not channel:
            return jsonify({"error": f"Channel {channel_name} not found"}), 404
            
        success = ChatMessageState.mark_channel_read(current_user.id, channel.id)
        if success:
            return "", 204
        else:
            return jsonify({"error": "Failed to mark channel as read"}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error marking channel as read: {str(e)}")
        return jsonify({"error": str(e)}), 500


@blueprint.route("/chat/channels/<channel_name>", methods=["DELETE"])
@login_required
def delete_channel(channel_name):
    """Delete a channel and all its messages"""
    try:
        # Don't allow deleting the general channel
        if channel_name == "general":
            return jsonify({"error": "Cannot delete the general channel"}), 400

        channel = Channel.query.filter_by(name=channel_name).first()
        if not channel:
            return jsonify({"error": f"Channel {channel_name} not found"}), 404

        if not current_user.is_admin:
            return jsonify({"error": "Unauthorized"}), 403

        # Delete all message states for this channel
        ChatMessageState.query.filter_by(channel_id=channel.id).delete()
        
        # Delete all messages in the channel
        Chat.query.filter_by(channel_id=channel.id).delete()
        
        # Delete the channel
        db.session.delete(channel)
        db.session.commit()

        # Emit WebSocket event for channel deletion
        current_app.socketio.emit("channel_deleted", {
            "name": channel_name
        })

        return "", 204
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting channel: {str(e)}")
        return jsonify({"error": str(e)}), 400


# WebSocket event handlers
@current_app.socketio.on("join")
def on_join(data):
    """Join a chat channel"""
    channel = data.get("channel")
    if channel:
        join_room(channel)
        emit("status", {"msg": f"{current_user.first_name} has joined the channel."}, room=channel)


@current_app.socketio.on("leave")
def on_leave(data):
    """Leave a chat channel"""
    channel = data.get("channel")
    if channel:
        leave_room(channel)
        emit("status", {"msg": f"{current_user.first_name} has left the channel."}, room=channel)


@blueprint.route("/chat/channel/<channel_name>")
@login_required
def chat_channel(channel_name):
    """Chat channel view"""
    channel = Channel.query.filter_by(name=channel_name).first_or_404()
    messages = channel.messages.order_by(Chat.created_at.desc()).limit(50).all()
    messages.reverse()  # Show in chronological order
    
    # Mark channel as read
    ChatMessageState.mark_channel_read(current_user.id, channel.id)
    
    if is_mobile():
        return render_template(
            "chat/channel-mobile.html",
            channel=channel,
            messages=messages,
            title=f"#{channel_name}"
        )
        
    # Return error or redirect for desktop
    return redirect(url_for('people_bp.chat'))
