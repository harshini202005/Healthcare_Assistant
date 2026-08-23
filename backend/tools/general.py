import logging
import os
from mistralai import Mistral

logger = logging.getLogger(__name__)

def is_health_related(question):
    """Check if the question is health-related using specific medical/health keywords only."""
    health_keywords = [
        # Medical conditions & symptoms
        'symptom', 'disease', 'condition', 'diagnosis', 'illness', 'disorder',
        'infection', 'fever', 'cough', 'headache', 'pain', 'ache', 'nausea', 'vomit',
        'diabetes', 'blood pressure', 'hypertension', 'asthma', 'arthritis', 'cancer',
        'allergy', 'allergic', 'rash', 'inflammation', 'fracture', 'injury', 'wound',
        # Treatments & healthcare
        'treatment', 'medicine', 'medication', 'prescription', 'therapy', 'cure',
        'surgery', 'vaccine', 'vaccination', 'dose', 'dosage', 'side effect',
        'doctor', 'physician', 'specialist', 'hospital', 'clinic', 'emergency',
        'healthcare', 'appointment', 'consultation', 'book', 'booking', 'schedule',
        'slot', 'visit', 'reserve', 'checkup', 'check-up',
        # Body systems
        'heart', 'lung', 'kidney', 'liver', 'brain', 'blood', 'bone', 'muscle',
        'immune', 'nervous system', 'digestive', 'respiratory', 'cardiovascular',
        # Nutrition & diet
        'nutrition', 'nutrient', 'vitamin', 'mineral', 'calorie', 'protein',
        'carbohydrate', 'cholesterol', 'diet plan', 'meal plan', 'dietary',
        'vegetarian', 'vegan', 'keto', 'gluten', 'lactose', 'diabetic diet',
        # Mental health
        'mental health', 'anxiety', 'depression', 'stress', 'insomnia', 'sleep disorder',
        'sleep', 'therapy', 'counseling', 'psychiatrist', 'psychologist',
        # Wellness & fitness
        'fitness', 'exercise', 'workout', 'wellness', 'healthy lifestyle',
        'weight loss', 'obesity', 'bmi', 'physical activity',
        # General health terms
        'health', 'medical', 'clinical', 'patient', 'healthy', 'unhealthy',
        'prevent', 'prevention', 'risk factor', 'chronic', 'acute'
    ]

    question_lower = question.lower()
    return any(keyword in question_lower for keyword in health_keywords)

def answer(question, context=None):
    """
    Answer general health and wellness questions.
    Only responds to health-related queries.
    
    Args:
        question: The health question to answer
        context: Additional context or patient information (optional)
    """
    logger.debug(f"TOOL CALLED: general_query")
    logger.debug(f"Question: {question}")
    logger.debug(f"Context: {context or 'None'}")
    
    # Validate that query is health-related
    if not is_health_related(question):
        logger.warning(f"Non-health question detected")
        return {
            "error": True,
            "message": "I can only assist with health-related questions.",
            "suggestion": "Please ask about health topics like:\n• Medical conditions and symptoms\n• Treatments and medications\n• Diet and nutrition\n• Exercise and fitness\n• Mental health and wellness\n• Healthcare appointments and services"
        }
    
    api_key = os.getenv("MISTRAL_API_KEY")
    
    if not api_key or api_key == "your-mistral-api-key-here":
        logger.warning(f"Mistral API key not configured, using template response")
        
        # Common health topics with responses
        health_knowledge = {
            "exercise": "Regular exercise is crucial for health. Aim for 150 minutes of moderate aerobic activity or 75 minutes of vigorous activity per week, plus strength training twice weekly.",
            "sleep": "Adults need 7-9 hours of quality sleep per night. Maintain a consistent sleep schedule and create a relaxing bedtime routine.",
            "water": "Stay hydrated by drinking 8-10 glasses (about 2 liters) of water daily. Increase intake during exercise or hot weather.",
            "diet": "A balanced diet includes fruits, vegetables, whole grains, lean proteins, and healthy fats. Limit processed foods, sugar, and sodium.",
            "stress": "Manage stress through exercise, meditation, deep breathing, adequate sleep, and connecting with others. Seek professional help if needed.",
            "vitamins": "A balanced diet usually provides necessary vitamins. Consult a doctor before taking supplements."
        }
        
        answer = "I'm a healthcare assistant. "
        for topic, info in health_knowledge.items():
            if topic in question.lower():
                answer = info
                break
        else:
            answer = "I can help with health questions. Could you please be more specific about your health concern?"
        
        return {
            "answer": answer,
            "source": "template",
            "disclaimer": "⚕️ This is general information. Please consult a healthcare professional for medical advice."
        }
    
    # Use Mistral AI for response
    client = Mistral(api_key=api_key)
    
    try:
        messages = [
            {
                "role": "system",
                "content": """You are a certified healthcare information assistant. Follow these rules strictly:

SCOPE: Only answer questions about medical conditions, symptoms, treatments, medications, nutrition, fitness, mental health, or healthcare services. For any other topic, reply: "I can only assist with health-related questions."

ACCURACY:
- Only state facts that are well-established in medical literature.
- If uncertain, say "I don't have enough information on this — please consult a doctor."
- Never invent drug names, dosages, or treatment protocols.
- Do not guess at diagnoses.

OUTPUT FORMAT:
1. Direct answer to the question (2-4 sentences max).
2. Key points as a short bullet list (if applicable).
3. End with: "⚕️ Consult a healthcare professional before making medical decisions."

HARD RULES:
- Never claim to diagnose a condition.
- Never recommend specific prescription drug doses.
- Never contradict emergency medical advice.
- If the question involves an emergency, always say: "Call emergency services (911) immediately." """
            },
            {
                "role": "user",
                "content": question
            }
        ]

        if context:
            messages.insert(1, {
                "role": "system",
                "content": f"Patient context (use only for relevance, do not expose): {context}"
            })
        
        response = client.chat.complete(
            model="mistral-small-latest",
            messages=messages
        )
        
        answer = response.choices[0].message.content
        
        logger.info(f"Response generated successfully")
        
        return {
            "answer": answer,
            "source": "mistral_ai",
            "disclaimer": "⚕️ This information is for educational purposes. Please consult a healthcare professional for personalized medical advice."
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}")
        return {
            "error": True,
            "message": f"Unable to process your question: {error_msg}",
            "suggestion": "Please try again or rephrase your health question."
        }
