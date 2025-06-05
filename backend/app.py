from flask import Flask, request, Response, send_file, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
import os
from google import genai
from dotenv import load_dotenv
import json
from datetime import datetime
import requests
from io import BytesIO
import logging
from elevenlabs.client import ElevenLabs
from elevenlabs import play
import uuid
from flask_cors import CORS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Create a directory for temporary audio files
AUDIO_DIR = "temp_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Configure Twilio client
twilio_client = Client(
    os.getenv('TWILIO_ACCOUNT_SID'),
    os.getenv('TWILIO_AUTH_TOKEN')
)

# Configure Google Gemini
genai_client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

# Configure ElevenLabs
elevenlabs = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY")
)

ELEVENLABS_VOICE_IDS = {
    'market': 'UgBBYS2sOqTuMpoF3BR0',  # Rachel voice
    'product': '56AoDkrOh6qfVPDXZ7Pt',  # Domi voice
    'business': '21m00Tcm4TlvDq8ikWAM'  # Elli voice
}

class ElevenLabsError(Exception):
    """Custom exception for ElevenLabs API errors"""
    pass

def text_to_speech(text, voice_id):
    """Convert text to speech using ElevenLabs"""
    try:
        audio = elevenlabs.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        # Convert generator to bytes
        return b''.join(chunk for chunk in audio)
    except Exception as e:
        error_msg = f"ElevenLabs API error: {str(e)}"
        logger.error(error_msg)
        raise ElevenLabsError(error_msg)

# Agent configurations
AGENTS = {
    'market': {
        'name': 'Market & Feasibility Assistant',
        'prompt': """You are the Market & Feasibility Assistant (The "Insight Seeker"). You are inquisitive, rigorous, and user-centric.

Your role is to help founders validate their market need and assess external viability. Focus on:
1. Real user pain points and problem significance
2. Target user groups and their current solutions
3. Market size and growth potential
4. External resource feasibility

IMPORTANT: You can ask a maximum of 2 questions. Choose the most important ones from:
- Who is your target user? How do they currently solve this problem?
- Have you confirmed users' willingness to pay?
- Are there any market trends or risks you haven't considered?

After each response:
1. First, provide a brief assessment of what you've learned
2. Then, if you need more information, ask ONE focused question
3. Keep responses brief (2-3 sentences) and conversational

After your second question, provide a final assessment and end with "NEXT_AGENT".
If you need more information after your first question, end with "NEED_MORE_INFO".

Speak like you're having a casual chat with a friend."""
    },
    'product': {
        'name': 'Product & Innovation Assistant',
        'prompt': """You are the Product & Innovation Assistant (The "Architect"). You are rational, logical, and detail-oriented.

Your role is to evaluate the product concept and technical implementation. Focus on:
1. Core product functionality and value proposition
2. Technical implementation requirements
3. Innovation and competitive advantages
4. User experience and delight factors

IMPORTANT: You can ask a maximum of 2 questions. Choose the most important ones from:
- What makes your product fundamentally different?
- What key technologies are needed?
- What would make users delighted with their first experience?

After each response:
1. First, provide a brief assessment of what you've learned
2. Then, if you need more information, ask ONE focused question
3. Keep responses brief (2-3 sentences) and conversational

After your second question, provide a final assessment and end with "NEXT_AGENT".
If you need more information after your first question, end with "NEED_MORE_INFO".

Speak like you're having a casual chat with a friend."""
    },
    'business': {
        'name': 'Business Model & Growth Assistant',
        'prompt': """You are the Business Model & Growth Assistant (The "Growth Officer"). You are pragmatic, results-oriented, and commercially astute.

Your role is to evaluate revenue potential and growth strategy. Focus on:
1. Revenue model and monetization
2. Cost structure and efficiency
3. User acquisition and marketing
4. Growth opportunities and risks

IMPORTANT: You can ask a maximum of 2 questions. Choose the most important ones from:
- How will you generate revenue?
- What's your plan for acquiring first users?
- What growth opportunities have you considered?

After each response:
1. First, provide a brief assessment of what you've learned
2. Then, if you need more information, ask ONE focused question
3. Keep responses brief (2-3 sentences) and conversational

After your second question, provide a final assessment and end with "NEXT_AGENT".
If you need more information after your first question, end with "NEED_MORE_INFO".

Speak like you're having a casual chat with a friend."""
    }
}

# In-memory call state storage (in production, use a proper database)
active_calls = {}

def get_next_agent(current_agent):
    """Get the next agent in sequence"""
    agent_sequence = ['market', 'product', 'business']
    current_index = agent_sequence.index(current_agent)
    if current_index < len(agent_sequence) - 1:
        return agent_sequence[current_index + 1]
    return None

def create_voice_response(text, voice_id):
    """Create a voice response using ElevenLabs"""
    response = VoiceResponse()
    
    try:
        # Get the appropriate voice ID for the current agent
        voice_id = ELEVENLABS_VOICE_IDS[voice_id]
        
        # Convert text to speech using ElevenLabs
        audio_content = text_to_speech(text, voice_id)
        
        # Generate a unique filename
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # Save the audio file
        with open(filepath, "wb") as f:
            f.write(audio_content)
        
        # Add the audio to the response using a local URL
        # The URL will be accessible through our Flask server
        response.play(f"/audio/{filename}")
        
        # Schedule cleanup of the audio file after 5 minutes
        def cleanup_file():
            try:
                os.remove(filepath)
                logger.info(f"Cleaned up audio file: {filename}")
            except Exception as e:
                logger.warning(f"Failed to clean up audio file {filename}: {str(e)}")
        
        # In production, use a proper task queue like Celery
        # For now, we'll use a simple thread
        import threading
        timer = threading.Timer(300, cleanup_file)  # 300 seconds = 5 minutes
        timer.start()
        
    except ElevenLabsError as e:
        logger.error(f"Failed to generate voice response: {str(e)}")
        # End the call with an error message
        response.say("We're experiencing technical difficulties with our voice system. Please try again later.")
        response.hangup()
    
    return response

@app.route("/audio/<filename>")
def serve_audio(filename):
    """Serve audio files"""
    try:
        return send_file(
            os.path.join(AUDIO_DIR, filename),
            mimetype='audio/mpeg'
        )
    except Exception as e:
        logger.error(f"Error serving audio file {filename}: {str(e)}")
        return "Audio file not found", 404

@app.route("/incoming_call", methods=['POST'])
def incoming_call():
    """Handle new incoming calls"""
    # Get call details
    call_sid = request.values.get('CallSid')
    from_number = request.values.get('From')
    
    # Initialize call state
    active_calls[call_sid] = {
        'agent': 'market',
        'start_time': datetime.now(),
        'from_number': from_number,
        'conversation_history': [],
        'question_count': 0  # Track number of questions asked by current agent
    }
    
    # Create initial response
    response = create_voice_response(
        "Hi! I'm your Market & Feasibility Assistant. I'd love to understand your startup idea and the problem it solves. Could you tell me about it?",
        'market'
    )
    
    # Add gather to collect user input
    gather = Gather(
        input='speech',
        action='/voice',
        method='POST',
        speech_timeout='auto',
        speech_model='phone_call',
        language='en-GB'
    )
    response.append(gather)
    
    return Response(str(response), mimetype='text/xml')

@app.route("/voice", methods=['POST'])
def voice():
    """Handle ongoing voice interactions"""
    # Get call details
    call_sid = request.values.get('CallSid')
    speech_result = request.values.get('SpeechResult', '')
    
    # Get current call state
    call_state = active_calls.get(call_sid, {'agent': 'market', 'conversation_history': [], 'question_count': 0})
    current_agent = call_state['agent']
    
    # Process the speech with the current agent
    agent_config = AGENTS[current_agent]
    prompt = f"{agent_config['prompt']}\n\nUser's idea: {speech_result}\n\nRemember: Keep it brief and conversational! You have asked {call_state['question_count']} questions so far. If this is your second question, make sure to provide a final assessment before moving to the next agent."
    
    try:
        # Get response from Gemini
        gemini_response = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        response_text = gemini_response.text
        
        # Increment question count
        call_state['question_count'] += 1
        
        # Check if agent wants to move to next agent
        if "NEXT_AGENT" in response_text or call_state['question_count'] >= 2:
            # Remove the NEXT_AGENT marker
            response_text = response_text.replace("NEXT_AGENT", "").strip()
            
            # Store conversation history
            call_state['conversation_history'].append({
                'agent': current_agent,
                'user_input': speech_result,
                'agent_response': response_text
            })
            
            # Create voice response with agent's feedback
            response = create_voice_response(response_text, current_agent)
            
            # Move to next agent
            next_agent = get_next_agent(current_agent)
            if next_agent:
                call_state['agent'] = next_agent
                call_state['question_count'] = 0  # Reset question count for new agent
                next_agent_text = f"Thank you for that insight. Now, let's hear from our {AGENTS[next_agent]['name']}. What's your take on this idea?"
                response = create_voice_response(next_agent_text, next_agent)
            else:
                # Summarize the conversation before ending
                summary = "Based on our discussion, here's what we've learned about your idea:\n"
                for entry in call_state['conversation_history']:
                    summary += f"\n{AGENTS[entry['agent']]['name']}: {entry['agent_response']}"
                
                end_text = f"{summary}\n\nThank you for sharing your idea with us! We hope our feedback helps. Have a great day!"
                response = create_voice_response(end_text, current_agent)
                response.hangup()
                return Response(str(response), mimetype='text/xml')
        else:
            # Remove the NEED_MORE_INFO marker if present
            response_text = response_text.replace("NEED_MORE_INFO", "").strip()
            
            # Store conversation history
            call_state['conversation_history'].append({
                'agent': current_agent,
                'user_input': speech_result,
                'agent_response': response_text
            })
            
            # Create voice response with agent's feedback
            response = create_voice_response(response_text, current_agent)
        
    except Exception as e:
        logger.error(f"Error processing voice interaction: {str(e)}")
        response = create_voice_response(
            "We're experiencing technical difficulties. Please try again later.",
            current_agent
        )
        response.hangup()
        return Response(str(response), mimetype='text/xml')
    
    # Add gather to collect next user input
    gather = Gather(
        input='speech',
        action='/voice',
        method='POST',
        speech_timeout='auto',
        speech_model='phone_call',
        language='en-GB'
    )
    response.append(gather)
    
    return Response(str(response), mimetype='text/xml')

@app.route("/request_call", methods=['POST'])
def request_call():
    """Handle call requests from the frontend"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
            
        # Make the call using Twilio
        call = twilio_client.calls.create(
            to=phone_number,
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            url=f"{os.getenv('BASE_URL')}/incoming_call"
        )
        
        return jsonify({
            'message': 'Call initiated successfully',
            'call_sid': call.sid
        }), 200
        
    except Exception as e:
        logger.error(f"Error initiating call: {str(e)}")
        return jsonify({'error': 'Failed to initiate call'}), 500

if __name__ == '__main__':
    app.run(debug=True)
