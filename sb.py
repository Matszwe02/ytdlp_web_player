import requests


class SponsorBlock:
    def __init__(self, video: str):
        self.video_id = video.split('?v=')[-1]
        self.categories = ["sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "music_offtopic"]
        self.url = f"https://sponsor.ajay.app/api/skipSegments"
        self.segments = []


    def get_segments(self) -> list[tuple[str, float, float]]:
        """
        Get sponsor segments from SponsorBlock API
        """
        
        try:
            
            params = {"videoID" : self.video_id, "category" : self.categories}
            response = requests.get(self.url, params=params)
            
            self.segments = []
            
            for seg in response.json():
                self.segments.append({"category": seg['category'], "start": seg['segment'][0], "end": seg['segment'][1]})
            return self.segments
            
        except Exception:
            return self.segments


    # def normalize_segments(self, video_duration: float):
    #     for id, seg in enumerate(self.segments):
    #         self.segments[id] = (seg[0], round(seg[1] / video_duration, 6), round(seg[2] / video_duration, 6))
    #         print(seg)
    #     return self.segments
