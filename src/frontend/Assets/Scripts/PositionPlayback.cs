using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class PositionPlayback : PlaybackView
{
    [SerializeField] private RawImage carTransform;
    [SerializeField] private RectTransform canvasRect;
    [SerializeField] private RectTransform circle1;
    [SerializeField] private RectTransform circle2;
    [SerializeField] private LineRenderer lineRenderer;
    private float previousTime;
    private Vector3 startPosition;
    private Vector3 endPosition;
    private float totalDistance;
    InputFields inputFields;
    private float angle;
    // Max Position will be changed
    private float maxPosition = 175;
    private float canvasWidth;

    private void Start()
    {
        inputFields = FindAnyObjectByType<InputFields>();
        angle = (float)inputFields.parameters.AngleOfIncline;
        canvasWidth = canvasRect.rect.width  -50;
        calcStartEndPositions();
    }

    public override void Display(DataPoint dataPoint)
    {
        if (previousTime == 0 || dataPoint.Time == 0)
        {
            if (angle != 0)
            {
                UpdateAngle(angle);
            }
            previousTime = dataPoint.Time;
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(startPosition.x, startPosition.y);
            return;
        }

        float elapsedTime = dataPoint.Time - previousTime;

        MoveCarAlongTrack(dataPoint.Position, angle);
        previousTime = dataPoint.Time;
    }

    private void calcStartEndPositions()
    {

        float halfCanvasWidth = canvasRect.rect.width / 2;
        float halfCanvasHeight = canvasRect.rect.height / 2;

        startPosition = new Vector3(-halfCanvasWidth+25, -halfCanvasHeight, 0);

        endPosition = new Vector3(halfCanvasWidth-25, -halfCanvasHeight, 0);
        
        totalDistance = canvasRect.rect.width-25;        

        if (angle != 0) {
            float radius = totalDistance;
            float xOffSet = radius * Mathf.Cos(angle*Mathf.Deg2Rad);
            float yOffSet = radius * Mathf.Sin(angle*Mathf.Deg2Rad);
            endPosition = new Vector3(startPosition.x + xOffSet, startPosition.y + yOffSet, 0);
        }
        circle1.anchoredPosition = new Vector2(startPosition.x, startPosition.y);
        circle2.anchoredPosition = new Vector2(endPosition.x, endPosition.y);
        Vector3 worldPos1 = circle1.position;  
        Vector3 worldPos2 = circle2.position;  
        lineRenderer.useWorldSpace = true;
        lineRenderer.positionCount = 2;
        lineRenderer.SetPosition(0, worldPos1);
        lineRenderer.SetPosition(1, worldPos2);
        circle1.gameObject.SetActive(false);
        circle2.gameObject.SetActive(false);

     }

    private void MoveCarAlongTrack(float position, float angle)
    {
        
        if (angle != 0)
        {
            float normalizedDistance = position / maxPosition;
            float radius = totalDistance;
            float xOffSet = radius * Mathf.Cos(angle*Mathf.Deg2Rad);
            float yOffSet = radius * Mathf.Sin(angle*Mathf.Deg2Rad);
            float x = startPosition.x + (normalizedDistance * xOffSet);
            float y = startPosition.y + (normalizedDistance * yOffSet);
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(x, y);
        }
        else
        {
            float normalizedXPos= ((position / maxPosition) * canvasWidth) - (canvasWidth / 2); 
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(normalizedXPos, startPosition.y);
        }
    }

    private void UpdateAngle(float angle)
    {
        carTransform.GetComponent<RectTransform>().rotation = Quaternion.Euler(0, 0, angle);
    }
}