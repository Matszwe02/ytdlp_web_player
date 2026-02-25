function doubleTapFF(options)
{
	var videoElement = this;
	var videoElementId = this.id();
	document.getElementById(videoElementId).addEventListener("touchstart", tapHandler);
	document.getElementById(videoElementId).addEventListener("touchmove", moveHandler);
	var tappedTwice = false;
    var tapTimer = null;
    var initialMoveDistance = null;

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
        if (e.touches.length > 1)
        {
            clearTapTimer();
            initialMoveDistance = null;
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

    function moveHandler(e)
    {
        if (e.touches.length > 1)
        {
            clearTapTimer();
        }
        if (e.touches.length === 2)
        {
            const x0 = e.touches[0].clientX;
            const y0 = e.touches[0].clientY;
            const x1 = e.touches[1].clientX;
            const y1 = e.touches[1].clientY;

            const dx = x1 - x0;
            const dy = y1 - y0;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (initialMoveDistance == null)
            {
                initialMoveDistance = distance;
            }
            else
            {
                const change = distance - initialMoveDistance;
                if (Math.abs(change) > 20)
                {
                    videoElement.controlBar.ZoomToFillToggle.handleClick(state = change > 0);
                    initialMoveDistance = distance;
                }
            }
        }
    }

}
videojs.registerPlugin('doubleTapFF', doubleTapFF);
