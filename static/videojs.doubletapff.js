function doubleTapFF(options) {
	var videoElement = this
	videoElementId = this.id();
	document.getElementById(videoElementId).addEventListener("touchstart", tapHandler);
	var tapedTwice = false;
	function tapHandler(e) {
    
        var br = document.getElementById(videoElementId).getBoundingClientRect();
        var x = e.touches[0].clientX - br.left;
        var y = e.touches[0].clientY - br.top;
        
        if (y > br.height * 0.8 || y < br.height * 0.2)
        {
            return false;
        }
        
        if (x > br.width * 0.33 && x < br.width * 0.67)
        {
            if (videoElement.hasClass('vjs-user-active') || videoElement.paused()) {
                if (videoElement.paused()) videoElement.play();
                else videoElement.pause();
            }
        }
    
		if (!videoElement.paused()) {

			if (!tapedTwice) {
				tapedTwice = true;
				setTimeout(function () {
					tapedTwice = false;
				}, 300);
				return false;
			}
			e.preventDefault();

			if (x <= br.width * 0.33)
            {
				videoElement.currentTime(videoElement.currentTime() - 10);
			}
            else if (x >= br.width * 0.67)
            {
				videoElement.currentTime(videoElement.currentTime() + 10);
			}
		}


	}
}
videojs.registerPlugin('doubleTapFF', doubleTapFF);
