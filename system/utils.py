
from flask import request


def is_mobile():
    """Check if the current request is from a mobile device"""
    user_agent = request.user_agent.string.lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'webos']
    return any(keyword in user_agent for keyword in mobile_keywords)
