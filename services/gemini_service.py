import google.generativeai as genai
from config.config import GEMINI_API_KEY
import logging
import asyncio
from PIL import Image
import io
import base64
from google.api_core import retry

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        # Optimize generation parameters for faster response
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 1024,  # Reduced for faster response
            "candidate_count": 1,
        }
        self.model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
        self.vision_model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)

    async def get_response(self, prompt, max_retries=3):
        for attempt in range(max_retries):
            try:
                # Add timeout to the event loop
                response = await asyncio.wait_for(
                    self._generate_content(prompt),
                    timeout=30.0  # 30 seconds timeout
                )
                return response
            except asyncio.TimeoutError:
                logger.error(f"Attempt {attempt + 1} timed out")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    return "I'm sorry, the request timed out. Please try again later."
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    return "I'm sorry, I'm having trouble processing your request right now. Please try again later."

    async def analyze_image(self, image_data, max_retries=3):
        for attempt in range(max_retries):
            try:
                # Convert bytearray to PIL Image
                image = Image.open(io.BytesIO(image_data))
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Optimize image size
                max_size = 768
                if max(image.size) > max_size:
                    ratio = max_size / max(image.size)
                    new_size = tuple(int(dim * ratio) for dim in image.size)
                    image = image.resize(new_size, Image.Resampling.LANCZOS)
                
                # Create a concise prompt
                prompt = [{
                    'role': 'user',
                    'parts': [{
                        'text': 'Describe this image briefly.'
                    }, {
                        'inline_data': {
                            'mime_type': 'image/jpeg',
                            'data': self._image_to_base64(image)
                        }
                    }]
                }]
                
                # Add timeout to the event loop
                response = await asyncio.wait_for(
                    self._analyze_image_content(prompt),
                    timeout=90.0
                )
                return response
            except asyncio.TimeoutError:
                logger.error(f"Image analysis attempt {attempt + 1} timed out")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    return "I'm sorry, the image analysis timed out. Please try with a smaller image or try again later."
            except Exception as e:
                logger.error(f"Image analysis attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    return "I'm sorry, I'm having trouble analyzing this image right now. Please try again later."

    def _image_to_base64(self, image):
        """Convert PIL Image to base64 string"""
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=85, optimize=True)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str

    async def _analyze_image_content(self, prompt):
        """Helper method to wrap the synchronous API call"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.vision_model.generate_content(prompt)
            )
            return response.text
        except Exception as e:
            logger.error(f"Error in _analyze_image_content: {str(e)}")
            raise

    async def _generate_content(self, prompt):
        """Helper method to wrap the synchronous API call"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: self.model.generate_content(prompt)
        )
        return response.text 