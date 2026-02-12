function doubleTapFF(options)
{
	var videoElement = this;
	var videoElementId = this.id();
	document.getElementById(videoElementId).addEventListener("touchstart", tapHandler);
	var tappedTwice = false;
    var tapTimer = null;

    function getTapTimer()
    {
        return tapTimer != null;
    }

    function clearTapTimer()
    {
        if (tapTimer != null)
        {
            clearTimeout(tapTimer);
            tapTimer = null;
        }
    }

    function setTapTimer(enableSingleTap = false)
    {
        if (tapTimer != null)
        {
            clearTapTimer();
        }
        tapTimer = setTimeout(() => {
            tapTimer = null;
            if (!tappedTwice && enableSingleTap)
            {
                if (videoElement.paused()) videoElement.play();
                else videoElement.pause();
            }
            tappedTwice = false;
        }, 300);
    }

	function tapHandler(e)
    {
        if (e.target?.tagName?.toLowerCase() != 'video')
        {
            return false;
        }

        var br = document.getElementById(videoElementId).getBoundingClientRect();
        var x = e.touches[0].clientX - br.left;
        var y = e.touches[0].clientY - br.top;
        
        if (y > br.height * 0.8 || y < br.height * 0.2)
        {
            return false;
        }
        
        if (x > br.width * 0.33 && x < br.width * 0.67)
        {
            if (videoElement.hasClass('vjs-user-active') || videoElement.paused())
            {
                if (videoElement.paused()) videoElement.play();
                else videoElement.pause();
            }
        }
        else
        {
            if (getTapTimer())
            {
                if (x <= br.width * 0.33)
                {
                    videoElement.currentTime(videoElement.currentTime() - 10);
                }
                else if (x >= br.width * 0.67)
                {
                    videoElement.currentTime(videoElement.currentTime() + 10);
                }
                tappedTwice = true;
                e.preventDefault();
            }
            setTapTimer((videoElement.hasClass('vjs-user-active') || videoElement.paused()));

        }
	}
}
videojs.registerPlugin('doubleTapFF', doubleTapFF);
