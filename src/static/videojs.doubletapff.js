function doubleTapFF(options)
{
	var videoElement = this;
	var videoElementId = this.id();
	document.getElementById(videoElementId).addEventListener("mousedown", clickHandler);
	document.getElementById(videoElementId).addEventListener("mouseup", clickEndHandler);
	document.getElementById(videoElementId).addEventListener("touchstart", tapHandler);
	document.getElementById(videoElementId).addEventListener("touchmove", moveHandler);
	document.getElementById(videoElementId).addEventListener("touchend", tapEndHandler);
	var tappedTwice = false;
    var tapTimer = null;
    var holdTimer = null;
    var playbackRate = null;
    var initialMoveDistance = null;

    function clearHoldTimer(e)
    {
        clearTimeout(holdTimer);
        if (playbackRate)
        {
            e.preventDefault();
            setTimeout(() => {
                videoElement.play();
            }, 50)
            videoElement.playbackRate(playbackRate);
            window.navigator?.vibrate?.(10);
        }
        playbackRate = null;;
    }

    function setHoldTimer()
    {
        if (videoElement.paused()) return;
        holdTimer = setTimeout(() => {
            if (playbackRate) return;
            playbackRate = videoElement.playbackRate();
            videoElement.playbackRate(playbackRate * 2);
            window.navigator?.vibrate?.(10);
        }, 500);
    }

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

    function clickHandler(e)
    {
        if (e.target?.tagName?.toLowerCase() != 'video' || e.target?.classList.contains('vjs-poster')) return;
        e.preventDefault();
        if (!getTapTimer()) setHoldTimer();
    }

    function clickEndHandler(e)
    {
        clearHoldTimer(e);
    }

	function tapHandler(e)
    {
        if (!(videoElement.hasClass('vjs-user-active') || videoElement.paused())) e.preventDefault();
        if (e.target?.tagName?.toLowerCase() != 'video' || e.target?.classList.contains('vjs-poster')) return;

        if (e.touches.length > 1)
        {
            clearTapTimer();
            clearHoldTimer();
            initialMoveDistance = null;
        }
        else
        {
            if (!getTapTimer()) setHoldTimer();
        }

        var br = document.getElementById(videoElementId).getBoundingClientRect();
        var x = e.touches[0].clientX - br.left;
        var y = e.touches[0].clientY - br.top;
        
        if (y > br.height * 0.8 || y < br.height * 0.2) return;
        
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
            clearHoldTimer();
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
                    videoElement.controlBar.ZoomToFillToggle.handleClick(null, change > 0);
                    initialMoveDistance = distance - (Math.sign(change) * 20);
                }
                videoElement.el().querySelector('video').style.scale = 1 + ((distance - initialMoveDistance) / 100);
            }
        }
    }

    function tapEndHandler(e)
    {
        clearHoldTimer(e);
        videoElement.el().querySelector('video').style.scale = 1;
    }

}
videojs.registerPlugin('doubleTapFF', doubleTapFF);
