using UnityEngine;

public class CarScript : MonoBehaviour
{
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        if (gameObject.transform.position.x > 10)
        {
            gameObject.transform.position = new Vector3(-10, 0, 0);
        }
        gameObject.transform.position += new Vector3(0.01f, 0, 0);
    }
}
