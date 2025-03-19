using UnityEngine;
using UnityEngine.UI;
using CommunicationProtocol.Receivers;
using System.IO;

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
    private float angle;
    private float distance;
    private float canvasWidth;

    private void Start()
    {
        InputParameters inputParameters = new InputParameters(PathConstants.INPUT_PARAMETERS_PATH);
        angle = float.Parse(inputParameters.GetValue(ParameterNames.ANGLE_OF_INCLINE));
        distance = float.Parse(inputParameters.GetValue(ParameterNames.TOTAL_DISTANCE));
        canvasWidth = canvasRect.rect.width  -50;
        calcStartEndPositions();
        SetCarInitial();
    }

    private void SetCarInitial()
    {
        // Set initial position
        carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(startPosition.x, startPosition.y);

        // Rotate the car before playback starts
        if (angle != 0)
        {
            carTransform.GetComponent<RectTransform>().rotation = Quaternion.Euler(0, 0, angle);
        }
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

        MoveCarAlongTrack(dataPoint.CarPosition, angle);
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
       
        DrawPath(circle1, circle2);

        circle1.gameObject.SetActive(false);
        circle2.gameObject.SetActive(false);

     }

    private void DrawPath(RectTransform startCircle, RectTransform endCircle)
    {
        Vector3 worldPos1 = startCircle.position;  
        Vector3 worldPos2 = endCircle.position;  
        
        lineRenderer.useWorldSpace = true;
        lineRenderer.startColor = new Color(0.7f, 0.5f, 0.3f);
        lineRenderer.material.color = new Color(0.7f, 0.5f, 0.3f);
        lineRenderer.endColor   = new Color(0.7f, 0.5f, 0.3f);

        lineRenderer.positionCount = 4;
        lineRenderer.SetPosition(0, worldPos1);
        lineRenderer.SetPosition(1, worldPos2);

        var baselinePoint = new Vector3(worldPos2.x, worldPos1.y, worldPos1.z);
        lineRenderer.SetPosition(2, baselinePoint);
        lineRenderer.SetPosition(3, worldPos1);
    }

    private void MoveCarAlongTrack(float position, float angle)
    {
        
        if (angle != 0)
        {
            float normalizedDistance = position / distance;
            float radius = totalDistance;
            float xOffSet = radius * Mathf.Cos(angle*Mathf.Deg2Rad);
            float yOffSet = radius * Mathf.Sin(angle*Mathf.Deg2Rad);
            float x = startPosition.x + (normalizedDistance * xOffSet);
            float y = startPosition.y + (normalizedDistance * yOffSet);
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(x, y);
        }
        else
        {
            float normalizedXPos= ((position / distance) * canvasWidth) - (canvasWidth / 2); 
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(normalizedXPos, startPosition.y);
        }
    }

    private void UpdateAngle(float angle)
    {
        carTransform.GetComponent<RectTransform>().rotation = Quaternion.Euler(0, 0, angle);
    }
}